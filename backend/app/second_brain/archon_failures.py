"""Shared Archon failure heuristics used by both ingest paths.

Two paths record Archon runs as ActionMemory entries:

1. ``second_brain.archon_ingest`` — startup scan of ``.archon`` log files.
2. ``archon_system.service._upsert_run_action_memory`` — live API sync.

This module is the single source of truth for failure categorization, log
parsing, and the canonical tag / metadata shape, so both paths produce
entries that downstream consumers (dreaming pattern extraction, gap
analysis, insights) can treat uniformly.
"""

import json
import re

_MAX_SUMMARY = 1500

# Ordered keyword rules → a coarse failure category used as a shared tag so that
# similar failures cluster together when the graph links nodes by tag.
CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("timeout", ("timed out", "timeout")),
    ("model-crash", ("model has crashed",)),
    ("model-not-found", ("model not found",)),
    ("worktree", ("worktree",)),
    ("stale-ctx", ("stale after session", "this.stalemessage")),
    ("no-resumable-run", ("no resumable run",)),
    ("already-active", ("already active on this path",)),
]

_RUN_ID_RE = re.compile(r'"workflowRunId"\s*:\s*"([0-9a-f]{16,40})"')


def categorize(text: str) -> str | None:
    """Map failure text to a coarse category via CATEGORY_RULES, else None."""
    low = text.lower()
    for cat, keywords in CATEGORY_RULES:
        if any(k in low for k in keywords):
            return cat
    return None


def extract_failure_summary(text: str) -> str | None:
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


def extract_workflow_name(text: str, fallback: str) -> str:
    m = re.search(r"Running workflow:\s*(\S+)", text)
    if m:
        return m.group(1)
    m = re.search(r"workflow '([^']+)'", text)
    if m:
        return m.group(1)
    return fallback


def extract_workflow_run_id(text: str) -> str | None:
    """Pull the Archon run id out of pino JSON log lines, if present."""
    m = _RUN_ID_RE.search(text)
    return m.group(1) if m else None


def canonical_tags(
    workflow: str | None, status: str, category: str | None
) -> list[str]:
    """Canonical tag set shared by both ingest paths.

    The ``archon:<category>`` tag is what dreaming's pattern extraction
    aggregates into top failure categories — keep that prefix stable.
    """
    tags = ["archon", workflow or "unknown-workflow", status]
    if status == "failed":
        tags.append("failure")
    if category:
        tags.append(f"archon:{category}")
    return list(dict.fromkeys(tags))


def canonical_metadata_core(
    workflow: str | None, category: str | None, errors: list[str] | None
) -> dict:
    """Metadata keys both ingest paths must write; path-specific extras may be added."""
    return {
        "workflow": workflow or "unknown-workflow",
        "category": category,
        "errors": errors or [],
    }
