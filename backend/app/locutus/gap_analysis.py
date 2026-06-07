"""Gap analysis — turns recurring failure patterns surfaced by the Dreaming cycle
into draft `ReasoningLog` proposals instead of leaving them buried in dream-diary prose.

Stage 2 of the autonomy transition plan (thoughts/locutus-autonomy-transition-plan.md):
detect, draft, dedupe — never auto-approve. Every proposal is created with
`status="draft"` and only a human can move it forward (Stage 3).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.locutus import service as locutus_service
from app.locutus.models import ReasoningLog
from app.locutus.schemas import SkillGap
from app.second_brain.action_models import ActionMemory

logger = logging.getLogger(__name__)

# An action_type must fail at least this many times within the analyzed window
# before it's considered a recurring gap worth proposing a skill for.
GAP_FAILURE_THRESHOLD = 3


def _aware(dt: datetime) -> datetime:
    """Normalize naive datetimes (from SQLite) to offset-aware UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def find_skill_gaps(
    actions: list[ActionMemory],
    threshold: int = GAP_FAILURE_THRESHOLD,
) -> list[SkillGap]:
    """Group failed ActionMemory entries by action_type and surface recurring ones.

    An action_type qualifies as a gap when it has accumulated at least `threshold`
    failures in the analyzed window. Returned gaps are sorted by failure_count desc.
    """
    failures_by_type: dict[str, list[ActionMemory]] = {}
    for action in actions:
        if action.status != "failed":
            continue
        failures_by_type.setdefault(action.action_type, []).append(action)

    gaps = [
        SkillGap(
            action_type=action_type,
            failure_count=len(failures),
            last_failure=max(_aware(a.created_at) for a in failures),
            suggested_skill_name=f"{action_type}-failure-recovery",
            suggested_skill_description=(
                f"Address recurring failures in '{action_type}' actions "
                f"({len(failures)}x in the analyzed window)."
            ),
        )
        for action_type, failures in failures_by_type.items()
        if len(failures) >= threshold
    ]
    gaps.sort(key=lambda g: -g.failure_count)
    return gaps


def _trigger_description(gap: SkillGap) -> str:
    return (
        f"Action type '{gap.action_type}' failed {gap.failure_count} times "
        f"in the analyzed window (most recently {gap.last_failure.strftime('%Y-%m-%d')})."
    )


def _expected_outcome(gap: SkillGap) -> str:
    return (
        f"Future '{gap.action_type}' actions succeed more often, reducing the "
        f"{gap.failure_count}x recurring failure pattern observed in this cycle."
    )


async def _draft_proposed_solution(gap: SkillGap, trigger_description: str) -> str:
    """Ask the LLM to draft a concrete technical solution for the gap.

    Falls back to a templated draft if the LLM is unreachable — gap analysis must
    never fail (or block the dreaming cycle) just because LM Studio is offline.
    """
    fallback = (
        f"Create a skill named '{gap.suggested_skill_name}' that addresses recurring "
        f"failures in '{gap.action_type}' actions: {gap.suggested_skill_description}"
    )

    try:
        from app.discord_bot.config import BotConfig
        from app.discord_bot.llm import LlmClient

        client = LlmClient(BotConfig.from_env().llm)
        await client.start()
        try:
            answer = await client.chat(
                [{
                    "role": "user",
                    "content": (
                        "Recurring problem detected during memory consolidation:\n"
                        f"{trigger_description}\n\n"
                        f"Suggested skill name: {gap.suggested_skill_name}\n\n"
                        "Draft a concrete technical solution (what should this skill do, "
                        "and how would it prevent the recurring failure?). Keep it to a "
                        "short paragraph."
                    ),
                }],
                "You are Locutus, a technical assistant drafting skill-creation proposals "
                "for human review. Be concrete and concise — no filler.",
            )
        finally:
            await client.stop()
        return answer.strip() or fallback
    except Exception as e:
        logger.warning(f"Gap analysis: LLM drafting failed, using templated fallback — {e}")
        return fallback


async def run_gap_analysis(
    db: AsyncSession,
    actions: list[ActionMemory],
    run_id: str | None = None,
) -> list[ReasoningLog]:
    """Scan actions for recurring failure patterns and draft `ReasoningLog` proposals.

    Dedupes by `trigger_description` — a gap that already produced a draft proposal
    (from a prior cycle) is skipped, so repeated dreaming cycles don't spam duplicates.
    Every created proposal is recorded in the audit trail and returned so the caller
    can notify about them; status always starts (and stays, here) at "draft".
    """
    created: list[ReasoningLog] = []

    for gap in find_skill_gaps(actions):
        trigger_description = _trigger_description(gap)

        existing = await db.execute(
            select(ReasoningLog).where(ReasoningLog.trigger_description == trigger_description)
        )
        if existing.scalar_one_or_none() is not None:
            continue

        proposed_solution = await _draft_proposed_solution(gap, trigger_description)

        log = await locutus_service.create_reasoning_log(
            db,
            title=f"Recurring failures in '{gap.action_type}'",
            trigger_description=trigger_description,
            proposed_solution=proposed_solution,
            expected_outcome=_expected_outcome(gap),
        )
        await locutus_service.record_action(
            db,
            action="gap_analysis_proposal",
            target=str(log.id),
            payload_summary=f"{log.title} — {gap.failure_count}x failures",
            run_id=run_id,
        )
        created.append(log)

    return created
