"""Ingest failed Archon workflow runs from .archon log files into ActionMemory.

Archon writes per-run logs to ``.archon/run-logs/`` and ``.archon/logs/`` (mixed
pino JSON + human-readable lines). This module scans those logs, detects runs
that failed, and records each as a ``status="failed"`` ActionMemory entry so the
failures surface in the Second Brain and the Obsidian graph.

Idempotent: each log maps to a stable ``source_ref`` — the Archon run id when it
can be extracted from the log (pino ``workflowRunId``), otherwise
``<subdir>/<filename>``. Refs already imported under ``source_kind="archon_run"``
are skipped, including runs that the live-API sync (``archon_system``) has
already mirrored under the same run id. Residual risk: a run whose log carries
no run id AND that is also mirrored from the live API yields two entries —
only possible for old log formats.
"""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.second_brain import action_service
from app.second_brain.action_models import ActionMemory
from app.second_brain.archon_failures import (
    canonical_metadata_core,
    canonical_tags,
    categorize,
    extract_failure_summary,
    extract_workflow_name,
    extract_workflow_run_id,
)

# This file: backend/app/second_brain/archon_ingest.py → parents[3] == repo root.
_DEFAULT_ARCHON_DIR = Path(__file__).resolve().parents[3] / ".archon"
_LOG_SUBDIRS = ("run-logs", "logs")
_SOURCE_KIND = "archon_run"


async def ingest_archon_run_failures(
    db: AsyncSession, archon_dir: Path | None = None
) -> dict:
    """Scan Archon log dirs and record failed runs as ActionMemory entries.

    Returns a small summary dict: scanned, created, skipped.
    """
    base = archon_dir or _DEFAULT_ARCHON_DIR
    result = {"scanned": 0, "created": 0, "skipped": 0}
    if not base.exists():
        return result

    rows = await db.execute(
        select(ActionMemory.source_ref).where(ActionMemory.source_kind == _SOURCE_KIND)
    )
    existing = {ref for (ref,) in rows.all() if ref}

    for sub in _LOG_SUBDIRS:
        log_dir = base / sub
        if not log_dir.is_dir():
            continue
        for log in sorted(log_dir.glob("*.log")):
            result["scanned"] += 1
            log_ref = f"{sub}/{log.name}"
            if log_ref in existing:
                result["skipped"] += 1
                continue
            try:
                text = log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            run_id = extract_workflow_run_id(text)
            if run_id and run_id in existing:
                # Already mirrored from the live Archon API under the run id.
                result["skipped"] += 1
                continue
            ref = run_id or log_ref

            summary = extract_failure_summary(text)
            if summary is None:
                continue  # run did not fail

            workflow = extract_workflow_name(text, log.stem)
            category = categorize(text)
            metadata = canonical_metadata_core(workflow, category, [summary])
            metadata["log_file"] = log_ref

            await action_service.create_action_memory(
                db,
                title=f"Archon failure: {log.stem}",
                description=summary,
                action_type="archon_run",
                status="failed",
                tags=canonical_tags(workflow, "failed", category),
                metadata=metadata,
                output_path=log_ref,
                source_kind=_SOURCE_KIND,
                source_ref=ref,
            )
            existing.add(ref)
            result["created"] += 1

    return result
