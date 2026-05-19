"""Service layer: fetch from Archon API, mirror to local DB, serve cached data on failure."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
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
