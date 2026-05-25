"""Ingest failed Archon workflow runs from .archon log files into ActionMemory.

Archon writes per-run logs to ``.archon/run-logs/`` and ``.archon/logs/`` (mixed
pino JSON + human-readable lines). This module scans those logs, detects runs
that failed, and records each as a ``status="failed"`` ActionMemory entry so the
failures surface in the Second Brain and the Obsidian graph.

Idempotent: each log maps to a stable ``source_ref`` (``<subdir>/<filename>``);
logs already imported under ``source_kind="archon_run"`` are skipped.
"""

import json
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.second_brain import action_service
from app.second_brain.action_models import ActionMemory

# This file: backend/app/second_brain/archon_ingest.py → parents[3] == repo root.
_DEFAULT_ARCHON_DIR = Path(__file__).resolve().parents[3] / ".archon"
_LOG_SUBDIRS = ("run-logs", "logs")
_SOURCE_KIND = "archon_run"
_MAX_SUMMARY = 1500

# Ordered keyword rules → a coarse failure category used as a shared tag so that
# similar failures cluster together when the graph links nodes by tag.
_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("timeout", ("timed out", "timeout")),
    ("model-crash", ("model has crashed",)),
    ("model-not-found", ("model not found",)),
    ("worktree", ("worktree",)),
    ("stale-ctx", ("stale after session", "this.stalemessage")),
    ("no-resumable-run", ("no resumable run",)),
    ("already-active", ("already active on this path",)),
]


def _extract_failure(text: str) -> str | None:
    """Return a concise failure summary if the log indicates a failed run, else None."""
    lines = text.splitlines()
    low = text.lower()

    failed = (
        '"anyfailed":true' in low
        or "completed with failures" in low
        or any(line.lstrip().startswith("❌") for line in lines)
        or any(line.strip().startswith("Error:") for line in lines)
    )
    if not failed:
        return None

    # Prefer the human-readable ❌ summary. Logs also print bare "❌" progress
    # markers, so collect non-empty ones and pick the most informative.
    cross = [
        c for line in lines
        if line.lstrip().startswith("❌") and (c := line.lstrip().lstrip("❌").strip())
    ]
    for c in cross:
        lc = c.lower()
        if "completed with failures" in lc or "completed with no successful" in lc:
            return c[:_MAX_SUMMARY]
    if cross:
        return max(cross, key=len)[:_MAX_SUMMARY]

    # Next: the last top-level "Error:" line.
    err_lines = [line.strip() for line in lines if line.strip().startswith("Error:")]
    if err_lines:
        return err_lines[-1][:_MAX_SUMMARY]

    # Fallback: a structured error log line (pino level 50).
    for line in lines:
        s = line.strip()
        if s.startswith("{") and '"level":50' in s:
            try:
                obj = json.loads(s)
            except json.JSONDecodeError:
                continue
            err = obj.get("err")
            msg = (err.get("message") if isinstance(err, dict) else None) or obj.get("msg")
            if msg:
                return str(msg)[:_MAX_SUMMARY]

    return "Workflow run failed (see log for details)."


def _workflow_name(text: str, fallback: str) -> str:
    m = re.search(r"Running workflow:\s*(\S+)", text)
    if m:
        return m.group(1)
    m = re.search(r"workflow '([^']+)'", text)
    if m:
        return m.group(1)
    return fallback


def _category(text: str) -> str | None:
    low = text.lower()
    for cat, keywords in _CATEGORY_RULES:
        if any(k in low for k in keywords):
            return cat
    return None


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
            ref = f"{sub}/{log.name}"
            if ref in existing:
                result["skipped"] += 1
                continue
            try:
                text = log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            summary = _extract_failure(text)
            if summary is None:
                continue  # run did not fail

            workflow = _workflow_name(text, log.stem)
            category = _category(text)
            tags = list(dict.fromkeys(
                ["archon", "failure", workflow] + ([category] if category else [])
            ))
            metadata = {"log_file": ref, "workflow": workflow}
            if category:
                metadata["category"] = category

            await action_service.create_action_memory(
                db,
                title=f"Archon failure: {log.stem}",
                description=summary,
                action_type="archon_run",
                status="failed",
                tags=tags,
                metadata=metadata,
                output_path=ref,
                source_kind=_SOURCE_KIND,
                source_ref=ref,
            )
            existing.add(ref)
            result["created"] += 1

    return result
