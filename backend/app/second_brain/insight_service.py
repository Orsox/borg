"""Service for Improvement Insights.

Groups recent failed ActionMemory entries by (category, workflow) and upserts
one ImprovementInsight per group. Regeneration is idempotent: insights keep
their identity via ``dedup_key``, acknowledged insights stay acknowledged,
and resolved insights reopen when new evidence arrives (regression detection).

Generation runs at the end of each dreaming cycle (see ``dreaming.service``)
and on demand via ``POST /api/brain/insights/generate`` — deliberately not on
every Archon sync to avoid needless SQLite write contention.
"""

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.second_brain.action_models import ActionMemory
from app.second_brain.archon_failures import categorize
from app.second_brain.insight_models import ImprovementInsight

logger = logging.getLogger(__name__)

_MAX_EVIDENCE = 20

_RECOMMENDATIONS: dict[str, str] = {
    "timeout": (
        "Increase step timeouts or split the workflow into smaller agents with "
        "fresh context — local-model nodes die on long prefill."
    ),
    "model-crash": (
        "Check local model stability (LM Studio / runner logs); consider a "
        "smaller model or a retry policy for the failing step."
    ),
    "model-not-found": (
        "The configured model is missing — verify the model id in the workflow "
        "config matches what the runner actually serves."
    ),
    "worktree": (
        "Clean up stale git worktrees before starting runs (git worktree prune) "
        "and make sure no two runs share a working path."
    ),
    "stale-ctx": (
        "Session context went stale — shorten long-running steps or restart the "
        "session before resuming the workflow."
    ),
    "no-resumable-run": (
        "Resume was attempted without a resumable run — start a fresh run or fix "
        "the run-state persistence."
    ),
    "already-active": (
        "A run was already active on the same path — serialize runs per codebase "
        "or use separate worktrees."
    ),
}
_FALLBACK_RECOMMENDATION = (
    "Investigate the recurring failures in this workflow — check the linked "
    "action memories for the full error narrative."
)


def _evidence_ids(insight: ImprovementInsight) -> list[int]:
    try:
        ids = json.loads(insight.evidence_refs)
        return [int(i) for i in ids] if isinstance(ids, list) else []
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def _resolve_category_workflow(action: ActionMemory) -> tuple[str, str | None]:
    """Determine (category, workflow) for a failed action from tags/metadata."""
    tags: list[str] = []
    try:
        loaded = json.loads(action.tags) if action.tags else []
        if isinstance(loaded, list):
            tags = [t for t in loaded if isinstance(t, str)]
    except json.JSONDecodeError:
        pass

    metadata: dict[str, Any] = {}
    try:
        loaded_meta = json.loads(action.metadata_json) if action.metadata_json else {}
        if isinstance(loaded_meta, dict):
            metadata = loaded_meta
    except json.JSONDecodeError:
        pass

    category = next(
        (t.split(":", 1)[1] for t in tags if t.startswith("archon:")), None
    )
    if not category:
        raw_cat = metadata.get("category")
        category = raw_cat if isinstance(raw_cat, str) and raw_cat else None
    if not category:
        errors = metadata.get("errors")
        error_text = "\n".join(e for e in errors if isinstance(e, str)) if isinstance(errors, list) else ""
        category = categorize(f"{action.description}\n{error_text}")
    if not category:
        category = "uncategorized"

    workflow = metadata.get("workflow") or metadata.get("workflow_name")
    if not isinstance(workflow, str) or not workflow:
        reserved = {"archon", "failure", "failed", "workflow-run", "has-errors"}
        workflow = next(
            (t for t in tags if t not in reserved and not t.startswith("archon:")),
            None,
        ) or action.action_type
    return category, workflow


def _summarize(actions: list[ActionMemory]) -> str:
    """Most frequent leading error line across the group, with occurrence count."""
    counter: Counter[str] = Counter()
    for action in actions:
        first_line = (action.description or "").strip().splitlines()
        if first_line:
            counter[first_line[0][:300]] += 1
    if not counter:
        return f"{len(actions)} failed run(s) in this group."
    message, count = counter.most_common(1)[0]
    return f"{message} ({count} of {len(actions)} failures)"


async def generate_insights(db: AsyncSession, days: int = 14) -> dict[str, Any]:
    """Derive/refresh insights from failed actions of the last ``days`` days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(ActionMemory).where(
            ActionMemory.status == "failed",
            ActionMemory.is_archived == False,  # noqa: E712
            ActionMemory.created_at >= cutoff,
        )
    )
    failed_actions = list(result.scalars().all())

    groups: dict[str, dict[str, Any]] = {}
    for action in failed_actions:
        category, workflow = _resolve_category_workflow(action)
        key = f"{category}:{workflow or '*'}"
        group = groups.setdefault(
            key, {"category": category, "workflow": workflow, "actions": []}
        )
        group["actions"].append(action)

    created = 0
    updated = 0
    now = datetime.now(timezone.utc)
    for key, group in groups.items():
        actions: list[ActionMemory] = group["actions"]
        actions.sort(key=lambda a: a.created_at)
        summary = _summarize(actions)
        recommendation = _RECOMMENDATIONS.get(group["category"], _FALLBACK_RECOMMENDATION)
        evidence = [a.id for a in actions]

        existing = (
            await db.execute(
                select(ImprovementInsight).where(ImprovementInsight.dedup_key == key)
            )
        ).scalar_one_or_none()

        if existing is None:
            db.add(
                ImprovementInsight(
                    dedup_key=key,
                    category=group["category"],
                    workflow=group["workflow"],
                    summary=summary,
                    recommendation=recommendation,
                    evidence_refs=json.dumps(evidence[-_MAX_EVIDENCE:]),
                    occurrences=len(actions),
                    status="open",
                    first_seen=actions[0].created_at,
                    last_seen=actions[-1].created_at,
                )
            )
            created += 1
            continue

        prior_ids = _evidence_ids(existing)
        new_ids = [i for i in evidence if i not in prior_ids]
        merged_evidence = (prior_ids + new_ids)[-_MAX_EVIDENCE:]
        has_new_evidence = bool(new_ids)
        if not has_new_evidence and existing.summary == summary:
            continue

        existing.summary = summary
        existing.recommendation = recommendation
        existing.evidence_refs = json.dumps(merged_evidence)
        # Evidence is capped, the occurrence counter is not.
        existing.occurrences = existing.occurrences + len(new_ids)
        existing.last_seen = actions[-1].created_at
        existing.updated_at = now
        # A resolved problem that recurs is a regression — reopen it.
        # Acknowledged insights stay acknowledged: the user already knows.
        if existing.status == "resolved" and has_new_evidence:
            existing.status = "open"
        updated += 1

    await db.commit()

    total_open = (
        await db.execute(
            select(func.count(ImprovementInsight.id)).where(
                ImprovementInsight.status == "open"
            )
        )
    ).scalar() or 0

    top = await get_top_insights(db, limit=5)
    return {
        "created": created,
        "updated": updated,
        "total_open": total_open,
        "top": [
            {
                "category": i.category,
                "workflow": i.workflow,
                "occurrences": i.occurrences,
                "recommendation": i.recommendation,
            }
            for i in top
        ],
    }


async def list_insights(
    db: AsyncSession, status: str = "open", page: int = 1, size: int = 20
) -> dict[str, Any]:
    query = select(ImprovementInsight)
    if status and status != "all":
        query = query.where(ImprovementInsight.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(
            ImprovementInsight.occurrences.desc(), ImprovementInsight.last_seen.desc()
        )
        .offset((page - 1) * size)
        .limit(size)
    )
    items = list((await db.execute(query)).scalars().all())
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, (total + size - 1) // size),
    }


async def get_top_insights(db: AsyncSession, limit: int = 3) -> list[ImprovementInsight]:
    result = await db.execute(
        select(ImprovementInsight)
        .where(ImprovementInsight.status == "open")
        .order_by(
            ImprovementInsight.occurrences.desc(), ImprovementInsight.last_seen.desc()
        )
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_insight(db: AsyncSession, insight_id: int) -> ImprovementInsight | None:
    result = await db.execute(
        select(ImprovementInsight).where(ImprovementInsight.id == insight_id)
    )
    return result.scalar_one_or_none()


async def set_status(
    db: AsyncSession, insight_id: int, status: str
) -> ImprovementInsight | None:
    insight = await get_insight(db, insight_id)
    if insight is None:
        return None
    insight.status = status
    insight.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(insight)
    return insight
