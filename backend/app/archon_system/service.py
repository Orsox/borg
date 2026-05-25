"""Service layer: fetch from Archon API, mirror to local DB, serve cached data on failure."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from app.second_brain.action_models import ActionMemory
from sqlalchemy.ext.asyncio import AsyncSession

from app.archon_system.client import ArchonClient, ArchonUnavailable
from app.archon_system.models import (
    ArchonCodebase,
    ArchonRun,
    ArchonSystemHealth,
    ArchonWorkflowMeta,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

async def _upsert_health(db: AsyncSession, data: dict[str, Any]) -> None:
    """Store the latest health snapshot."""
    # Always keep only the latest row
    await db.execute(delete(ArchonSystemHealth))
    active_platforms_raw = data.get("activePlatforms") or data.get("active_platforms") or []
    if isinstance(active_platforms_raw, str):
        try:
            active_platforms_raw = json.loads(active_platforms_raw)
        except Exception:
            active_platforms_raw = []

    concurrency_raw = data.get("concurrency") or {}

    health = ArchonSystemHealth(
        online=True,
        version=data.get("version"),
        adapter=data.get("adapter"),
        is_docker=data.get("is_docker", False),
        running_workflows=data.get("runningWorkflows") or data.get("running_workflows", 0),
        active_platforms=json.dumps(active_platforms_raw),
        checked_at=_now(),
    )
    db.add(health)
    await db.commit()


async def _get_cached_health(db: AsyncSession) -> ArchonSystemHealth | None:
    result = await db.execute(select(ArchonSystemHealth).order_by(ArchonSystemHealth.id.desc()).limit(1))
    return result.scalar_one_or_none()


async def sync_and_get_health(db: AsyncSession) -> dict[str, Any]:
    """Fetch health from Archon, mirror to DB, return response dict."""
    try:
        async with ArchonClient() as client:
            data = await client.get_health()
        await _upsert_health(db, data)
        cached_row = await _get_cached_health(db)
        platforms = json.loads(cached_row.active_platforms) if cached_row else []
        return {
            "online": True,
            "archon_url": "",
            "version": cached_row.version,
            "adapter": cached_row.adapter,
            "is_docker": cached_row.is_docker,
            "active_platforms": platforms,
            "running_workflows": cached_row.running_workflows,
            "concurrency": None,
            "checked_at": cached_row.checked_at.isoformat() if cached_row else None,
            "cached": False,
        }
    except ArchonUnavailable:
        cached_row = await _get_cached_health(db)
        if cached_row:
            platforms = json.loads(cached_row.active_platforms)
            return {
                "online": False,
                "archon_url": "",
                "version": cached_row.version,
                "adapter": cached_row.adapter,
                "is_docker": cached_row.is_docker,
                "active_platforms": platforms,
                "running_workflows": cached_row.running_workflows,
                "concurrency": None,
                "checked_at": cached_row.checked_at.isoformat(),
                "cached": True,
            }
        return {
            "online": False,
            "archon_url": "",
            "version": None,
            "adapter": None,
            "is_docker": False,
            "active_platforms": [],
            "running_workflows": 0,
            "concurrency": None,
            "checked_at": None,
            "cached": True,
        }


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def _normalize_action_status(status: str | None) -> str:
    normalized = (status or "unknown").strip().lower()
    if normalized in {"running", "queued", "pending", "in_progress"}:
        return "in_progress"
    if normalized in {"completed", "complete", "success", "succeeded", "done", "passed"}:
        return "success"
    if normalized in {"failed", "error", "cancelled", "canceled", "timeout", "timed_out"}:
        return "failed"
    return "in_progress"


def _extract_run_errors(raw: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    def _collect_from(source: dict[str, Any]) -> None:
        for key in ("error", "last_error", "failure_reason", "stderr", "rejection_reason"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                errors.append(value.strip())
        raw_errors = source.get("errors")
        if isinstance(raw_errors, list):
            for item in raw_errors:
                if isinstance(item, str) and item.strip():
                    errors.append(item.strip())
                elif isinstance(item, dict):
                    message = item.get("message") or item.get("error") or item.get("detail")
                    if isinstance(message, str) and message.strip():
                        errors.append(message.strip())

    # Top-level fields (fallback / older Archon payloads)
    _collect_from(raw)
    # Real Archon dashboard payloads nest the failure under `metadata`
    metadata = raw.get("metadata")
    if isinstance(metadata, dict):
        _collect_from(metadata)

    deduped: list[str] = []
    seen: set[str] = set()
    for error in errors:
        if error not in seen:
            seen.add(error)
            deduped.append(error)
    return deduped


def _collect_error_signals(raw: dict[str, Any]) -> dict[str, Any]:
    """Detect any error signal on a run, even when the overall status is not failed."""
    messages = _extract_run_errors(raw)
    try:
        agents_failed = int(raw.get("agents_failed") or 0)
    except (TypeError, ValueError):
        agents_failed = 0
    step_failed = str(raw.get("current_step_status") or "").strip().lower() in {"failed", "error"}
    status_failed = _normalize_action_status(raw.get("status")) == "failed"
    has_errors = bool(messages) or agents_failed > 0 or step_failed or status_failed
    return {
        "messages": messages,
        "agents_failed": agents_failed,
        "step_failed": step_failed,
        "status_failed": status_failed,
        "has_errors": has_errors,
    }


def _merge_errors(prior: Any, new: list[str]) -> list[str]:
    """Accumulate error messages across syncs, dedup preserving order."""
    merged: list[str] = []
    seen: set[str] = set()
    for source in (prior if isinstance(prior, list) else [], new):
        for error in source:
            if isinstance(error, str) and error.strip() and error not in seen:
                seen.add(error)
                merged.append(error)
    return merged


async def _upsert_run_action_memory(db: AsyncSession, raw: dict[str, Any], mapped: dict[str, Any]) -> None:
    archon_run_id = mapped["archon_run_id"]
    if not archon_run_id:
        return

    action_status = _normalize_action_status(mapped.get("status"))
    signals = _collect_error_signals(raw)
    user_message = (mapped.get("user_message") or "").strip()

    result = await db.execute(
        select(ActionMemory).where(
            ActionMemory.source_kind == "archon_run",
            ActionMemory.source_ref == archon_run_id,
        )
    )
    action = result.scalar_one_or_none()

    # Accumulate errors across syncs so transient/recovered errors are not lost.
    prior_errors: list[str] = []
    if action is not None:
        prior_metadata = json.loads(action.metadata_json) if action.metadata_json else {}
        if isinstance(prior_metadata, dict):
            prior_errors = prior_metadata.get("errors") or []
    accumulated_errors = _merge_errors(prior_errors, signals["messages"])

    description_parts = [
        f"Archon workflow run for '{mapped.get('workflow_name') or 'unknown-workflow'}'.",
        f"Current Archon status: {mapped.get('status') or 'unknown'}.",
    ]
    if mapped.get("codebase_name"):
        description_parts.append(f"Codebase: {mapped['codebase_name']}.")
    if user_message:
        description_parts.append(f"Request: {user_message}")
    if signals["has_errors"]:
        error_section = ["Fehler / Warnungen:"]
        if signals["agents_failed"]:
            error_section.append(f"Failed agents: {signals['agents_failed']}.")
        if signals["step_failed"] and raw.get("current_step_name"):
            error_section.append(f"Failed step: {raw['current_step_name']}.")
        if accumulated_errors:
            error_section.append("\n".join(accumulated_errors))
        description_parts.append("\n".join(error_section))

    raw_metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    metadata = {
        "archon_run_id": archon_run_id,
        "workflow_name": mapped.get("workflow_name"),
        "archon_status": mapped.get("status"),
        "user_message": mapped.get("user_message"),
        "started_at": mapped.get("started_at"),
        "last_activity_at": mapped.get("last_activity_at"),
        "completed_at": mapped.get("completed_at"),
        "codebase_name": mapped.get("codebase_name"),
        "working_path": mapped.get("working_path"),
        "agents_total": raw.get("agents_total"),
        "agents_completed": raw.get("agents_completed"),
        "agents_failed": signals["agents_failed"],
        "current_step_name": raw.get("current_step_name"),
        "current_step_status": raw.get("current_step_status"),
        "has_errors": signals["has_errors"],
        "error_count": len(accumulated_errors),
        "errors": accumulated_errors,
        # Full Archon run metadata (complete error narrative / output) kept untruncated.
        "archon_metadata": raw_metadata,
    }

    tags = [
        "archon",
        "workflow-run",
        mapped.get("workflow_name") or "unknown-workflow",
        mapped.get("status") or "unknown",
    ]
    if signals["has_errors"]:
        tags.append("has-errors")

    if action is None:
        action = ActionMemory(
            title=f"Archon Run: {archon_run_id}",
            description="\n\n".join(description_parts),
            action_type="archon_workflow_run",
            tools_used=json.dumps(["archon", "workflow-monitor"]),
            status=action_status,
            is_archived=False,
            duration_ms=None,
            output_path=mapped.get("working_path"),
            metadata_json=json.dumps(metadata),
            tags=json.dumps(tags),
            source_kind="archon_run",
            source_ref=archon_run_id,
        )
        db.add(action)
        return

    action.title = f"Archon Run: {archon_run_id}"
    action.description = "\n\n".join(description_parts)
    action.action_type = "archon_workflow_run"
    action.tools_used = json.dumps(["archon", "workflow-monitor"])
    action.status = action_status
    action.output_path = mapped.get("working_path")
    action.metadata_json = json.dumps(metadata)
    action.tags = json.dumps(tags)
    action.updated_at = _now()


def _map_run(raw: dict[str, Any]) -> dict[str, Any]:
    """Map raw Archon run data to our snake_case shape."""
    return {
        "archon_run_id": raw.get("id", ""),
        "workflow_name": raw.get("workflow_name", raw.get("workflowName", "")),
        "status": raw.get("status", "unknown"),
        "user_message": raw.get("user_message", raw.get("userMessage")),
        "started_at": raw.get("started_at", raw.get("startedAt")),
        "last_activity_at": raw.get("last_activity_at", raw.get("lastActivityAt")),
        "completed_at": raw.get("completed_at", raw.get("completedAt")),
        "codebase_name": raw.get("codebase_name", raw.get("codebaseName")),
        "working_path": raw.get("working_path", raw.get("workingPath")),
    }


async def _upsert_runs(db: AsyncSession, raw_runs: list[dict[str, Any]]) -> int:
    now = _now()
    for raw in raw_runs:
        mapped = _map_run(raw)
        archon_run_id = mapped["archon_run_id"]
        if not archon_run_id:
            continue
        # Upsert: delete old, insert new
        await db.execute(delete(ArchonRun).where(ArchonRun.archon_run_id == archon_run_id))
        run = ArchonRun(
            archon_run_id=archon_run_id,
            workflow_name=mapped["workflow_name"],
            status=mapped["status"],
            user_message=mapped["user_message"],
            started_at=mapped["started_at"],
            last_activity_at=mapped["last_activity_at"],
            completed_at=mapped["completed_at"],
            codebase_name=mapped["codebase_name"],
            working_path=mapped["working_path"],
            synced_at=now,
        )
        db.add(run)
        await _upsert_run_action_memory(db, raw, mapped)
    await db.commit()
    return len(raw_runs)


async def sync_and_get_runs(db: AsyncSession, status: str = "all", limit: int = 20) -> dict[str, Any]:
    try:
        async with ArchonClient() as client:
            raw_runs = await client.get_runs()
        await _upsert_runs(db, raw_runs)
    except ArchonUnavailable:
        logger.warning("Archon unavailable, serving cached runs")

    query = select(ArchonRun).order_by(ArchonRun.synced_at.desc())
    if status and status.lower() != "all":
        query = query.where(ArchonRun.status == status.lower())
    query = query.limit(limit)

    result = await db.execute(query)
    runs = list(result.scalars().all())

    items = [
        {
            "id": r.archon_run_id,
            "workflow_name": r.workflow_name,
            "status": r.status,
            "user_message": r.user_message,
            "started_at": r.started_at,
            "last_activity_at": r.last_activity_at,
            "completed_at": r.completed_at,
            "codebase_name": r.codebase_name,
            "working_path": r.working_path,
        }
        for r in runs
    ]
    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# Codebases
# ---------------------------------------------------------------------------

async def _upsert_codebases(db: AsyncSession, raw_codebases: list[dict[str, Any]]) -> int:
    now = _now()
    for raw in raw_codebases:
        archon_id = raw.get("id", "")
        if not archon_id:
            continue
        await db.execute(delete(ArchonCodebase).where(ArchonCodebase.archon_id == archon_id))
        cb = ArchonCodebase(
            archon_id=archon_id,
            name=raw.get("name", ""),
            repository_url=raw.get("repository_url", raw.get("repositoryUrl")),
            default_branch=raw.get("default_branch", raw.get("defaultBranch")),
            ai_assistant_type=raw.get("ai_assistant_type", raw.get("aiAssistantType")),
            synced_at=now,
        )
        db.add(cb)
    await db.commit()
    return len(raw_codebases)


async def sync_and_get_codebases(db: AsyncSession) -> dict[str, Any]:
    try:
        async with ArchonClient() as client:
            raw_codebases = await client.get_codebases()
        await _upsert_codebases(db, raw_codebases)
    except ArchonUnavailable:
        logger.warning("Archon unavailable, serving cached codebases")

    result = await db.execute(select(ArchonCodebase).order_by(ArchonCodebase.name))
    codebases = list(result.scalars().all())

    items = [
        {
            "id": cb.archon_id,
            "name": cb.name,
            "repository_url": cb.repository_url,
            "default_branch": cb.default_branch,
            "ai_assistant_type": cb.ai_assistant_type,
        }
        for cb in codebases
    ]
    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

async def _upsert_workflows(db: AsyncSession, raw_workflows: list[dict[str, Any]]) -> int:
    now = _now()
    for raw in raw_workflows:
        # Archon wraps workflow info in a "workflow" key
        wf = raw.get("workflow", raw)
        name = wf.get("name", "")
        if not name:
            continue
        # Strip nodes/steps to keep payload small
        await db.execute(delete(ArchonWorkflowMeta).where(ArchonWorkflowMeta.name == name))
        wfm = ArchonWorkflowMeta(
            name=name,
            description=wf.get("description"),
            provider=wf.get("provider"),
            source=raw.get("source", "unknown"),
            synced_at=now,
        )
        db.add(wfm)
    await db.commit()
    return len(raw_workflows)


async def sync_and_get_workflows(db: AsyncSession) -> dict[str, Any]:
    try:
        async with ArchonClient() as client:
            raw_workflows = await client.get_workflows()
        await _upsert_workflows(db, raw_workflows)
    except ArchonUnavailable:
        logger.warning("Archon unavailable, serving cached workflows")

    result = await db.execute(select(ArchonWorkflowMeta).order_by(ArchonWorkflowMeta.name))
    workflows = list(result.scalars().all())

    items = [
        {
            "name": wf.name,
            "description": wf.description,
            "provider": wf.provider,
            "source": wf.source,
        }
        for wf in workflows
    ]
    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# Full sync
# ---------------------------------------------------------------------------

async def sync_all(db: AsyncSession) -> dict[str, Any]:
    """Trigger a full sync of all Archon data."""
    now_iso = _now().isoformat()
    try:
        async with ArchonClient() as client:
            health_data = await client.get_health()
            raw_runs = await client.get_runs()
            raw_codebases = await client.get_codebases()
            raw_workflows = await client.get_workflows()
        await _upsert_health(db, health_data)
        runs_count = await _upsert_runs(db, raw_runs)
        codebases_count = await _upsert_codebases(db, raw_codebases)
        workflows_count = await _upsert_workflows(db, raw_workflows)
        return {
            "synced_at": now_iso,
            "health_updated": True,
            "runs_count": runs_count,
            "codebases_count": codebases_count,
            "workflows_count": workflows_count,
        }
    except ArchonUnavailable as e:
        logger.warning(f"Archon sync failed: {e}")
        return {
            "synced_at": now_iso,
            "health_updated": False,
            "runs_count": 0,
            "codebases_count": 0,
            "workflows_count": 0,
        }
