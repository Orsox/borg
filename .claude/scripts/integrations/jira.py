"""Jira integration — fetch and triage tickets.

Auth:
  Jira Server/DC  → JIRA_URL + JIRA_TOKEN (Personal Access Token)
  Jira Cloud      → JIRA_URL + JIRA_TOKEN (API Token) + JIRA_EMAIL + JIRA_CLOUD=true

Set these in borg/.env.
"""
import os
import re
import pathlib

from .registry import is_enabled


def _require_enabled():
    if not is_enabled("jira"):
        raise RuntimeError("Jira not configured. Add JIRA_URL and JIRA_TOKEN to .env")


def _get_client():
    from atlassian import Jira
    url = os.environ["JIRA_URL"]
    token = os.environ["JIRA_TOKEN"]
    if os.environ.get("JIRA_CLOUD", "").lower() == "true":
        return Jira(url=url, username=os.environ.get("JIRA_EMAIL", ""), password=token, cloud=True)
    return Jira(url=url, token=token)


def _run_jql(jql: str, limit: int = 50) -> list[dict]:
    client = _get_client()
    try:
        result = client.enhanced_jql(jql, limit=limit)
    except AttributeError:
        result = client.jql(jql, limit=limit)
    if isinstance(result, dict):
        return result.get("issues", [])
    return result or []


def _parse_issue(issue: dict) -> dict:
    f = issue.get("fields", {})
    desc = f.get("description") or ""
    # Jira Cloud description is Atlassian Document Format (dict), Server is plain text
    if isinstance(desc, dict):
        # Extract plain text from ADF
        desc = " ".join(
            node.get("text", "")
            for block in desc.get("content", [])
            for node in block.get("content", [])
            if node.get("type") == "text"
        )
    return {
        "key": issue.get("key", ""),
        "summary": f.get("summary", ""),
        "status": (f.get("status") or {}).get("name", ""),
        "priority": (f.get("priority") or {}).get("name", ""),
        "assignee": (f.get("assignee") or {}).get("displayName", "Unassigned"),
        "reporter": (f.get("reporter") or {}).get("displayName", ""),
        "created": (f.get("created") or "")[:10],
        "updated": (f.get("updated") or "")[:10],
        "description_preview": desc[:200].strip(),
    }


def _load_project_keys() -> list[str]:
    """Read JIRA_PROJECT_KEYS from USER.md or env."""
    env_keys = os.environ.get("JIRA_PROJECT_KEYS", "")
    if env_keys:
        return [k.strip() for k in env_keys.split(",") if k.strip()]
    user_md = pathlib.Path.home() / "Memory" / "USER.md"
    if not user_md.exists():
        return []
    match = re.search(r"JIRA_PROJECT_KEYS:\s*\[([^\]]*)\]", user_md.read_text())
    if not match:
        return []
    return [k.strip() for k in match.group(1).split(",") if k.strip()]


def get_new_tickets(project_keys: list[str] | None = None, days: int = 3) -> list[dict]:
    """Tickets created in the last N days across Orsox's projects."""
    _require_enabled()
    keys = project_keys or _load_project_keys()
    if not keys:
        return []
    jql = (
        f"project IN ({','.join(keys)})"
        f" AND status IN ('To Do','Open','Backlog')"
        f" AND created >= -{days}d"
        f" ORDER BY created DESC"
    )
    return [_parse_issue(i) for i in _run_jql(jql)]


def get_my_tickets() -> list[dict]:
    """All open tickets assigned to me."""
    _require_enabled()
    jql = "assignee = currentUser() AND status NOT IN ('Done','Closed') ORDER BY updated DESC"
    return [_parse_issue(i) for i in _run_jql(jql, limit=30)]


def get_overdue() -> list[dict]:
    """Tickets assigned to me with a passed due date."""
    _require_enabled()
    jql = (
        "assignee = currentUser()"
        " AND due < now()"
        " AND status NOT IN ('Done','Closed')"
        " ORDER BY due ASC"
    )
    return [_parse_issue(i) for i in _run_jql(jql, limit=20)]


def format_context(project_keys: list[str] | None = None) -> str:
    """Human-readable summary for CLI output or heartbeat context."""
    tickets = get_new_tickets(project_keys=project_keys)
    if not tickets:
        return "No new Jira tickets in the last 3 days."
    lines = [f"## Jira — New Tickets ({len(tickets)})"]
    for t in tickets:
        pri = f"[{t['priority']}] " if t['priority'] else ""
        lines.append(f"\n  {t['key']}  {pri}{t['summary']}")
        lines.append(f"  Status: {t['status']} | Assignee: {t['assignee']} | Created: {t['created']}")
        if t["description_preview"]:
            lines.append(f"  {t['description_preview'][:120]}…")
    return "\n".join(lines)
