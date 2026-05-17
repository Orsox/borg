"""Polarion ALM integration — read work items and recent changes.

Auth: Personal Access Token
  Polarion UI → My Profile → Personal Access Tokens → Generate

Set POLARION_URL and POLARION_TOKEN in borg/.env.
"""
import os
import re
import pathlib

from .registry import is_enabled


def _require_enabled():
    if not is_enabled("polarion"):
        raise RuntimeError("Polarion not configured. Add POLARION_URL and POLARION_TOKEN to .env")


def _get_client():
    from polarion_rest_api_client import OpenApiClient
    return OpenApiClient(
        polarion_url=os.environ["POLARION_URL"],
        token=os.environ["POLARION_TOKEN"],
        verify_ssl=True,
    )


def _load_project_ids() -> list[str]:
    """Read POLARION_PROJECT_IDS from USER.md or env."""
    env_ids = os.environ.get("POLARION_PROJECT_IDS", "")
    if env_ids:
        return [p.strip() for p in env_ids.split(",") if p.strip()]
    user_md = pathlib.Path.home() / "Memory" / "USER.md"
    if not user_md.exists():
        return []
    match = re.search(r"POLARION_PROJECT_IDS:\s*\[([^\]]*)\]", user_md.read_text())
    if not match:
        return []
    return [p.strip() for p in match.group(1).split(",") if p.strip()]


def _parse_item(item) -> dict:
    """Normalize a Polarion work item to a plain dict."""
    return {
        "id": getattr(item, "id", ""),
        "title": getattr(item, "title", ""),
        "type": getattr(item, "type", ""),
        "status": str(getattr(item, "status", "")),
        "assignee": str(getattr(item, "assignee", "Unassigned")),
        "updated": str(getattr(item, "updated", "")),
    }


def get_open_items(project_id: str | None = None) -> list[dict]:
    """Fetch open requirements/work items from Polarion."""
    _require_enabled()
    client = _get_client()
    project_ids = [project_id] if project_id else _load_project_ids()
    if not project_ids:
        return []

    results = []
    for pid in project_ids:
        try:
            pc = client.generate_project_client(project_id=pid)
            items = pc.get_work_items(query="status.open:true")
            results.extend(_parse_item(i) for i in items)
        except Exception as e:
            results.append({"id": f"ERROR:{pid}", "title": str(e), "type": "", "status": "error", "assignee": "", "updated": ""})
    return results


def get_recent_changes(days: int = 1, project_id: str | None = None) -> list[dict]:
    """Work items modified in the last N days."""
    _require_enabled()
    client = _get_client()
    project_ids = [project_id] if project_id else _load_project_ids()
    if not project_ids:
        return []

    results = []
    for pid in project_ids:
        try:
            pc = client.generate_project_client(project_id=pid)
            items = pc.get_work_items(query=f"updated:[NOW-{days}DAY TO NOW]")
            results.extend(_parse_item(i) for i in items)
        except Exception as e:
            results.append({"id": f"ERROR:{pid}", "title": str(e), "type": "", "status": "error", "assignee": "", "updated": ""})
    return results


def format_context(project_id: str | None = None) -> str:
    """Human-readable summary of recent Polarion changes."""
    items = get_recent_changes(project_id=project_id)
    if not items:
        return "No Polarion work item changes in the last 24h."
    lines = [f"## Polarion — Recent Changes ({len(items)})"]
    for i in items:
        lines.append(f"  {i['id']}  [{i['type']}]  {i['title']}")
        lines.append(f"  Status: {i['status']} | Assignee: {i['assignee']} | Updated: {i['updated']}")
    return "\n".join(lines)
