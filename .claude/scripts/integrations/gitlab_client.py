"""GitLab integration — commits and MRs across Orsox's projects.

Auth: Personal Access Token with read_api scope
  GitLab → User Settings → Access Tokens → Add new token → scope: read_api

Set GITLAB_URL and GITLAB_TOKEN in borg/.env.
"""
import os
import re
import pathlib
import datetime

from .registry import is_enabled


def _require_enabled():
    if not is_enabled("gitlab"):
        raise RuntimeError("GitLab not configured. Add GITLAB_URL and GITLAB_TOKEN to .env")


def _get_client():
    import gitlab
    return gitlab.Gitlab(
        url=os.environ["GITLAB_URL"],
        private_token=os.environ["GITLAB_TOKEN"],
    )


def _load_namespaces() -> list[str]:
    """Read GITLAB_MY_NAMESPACES from USER.md or env."""
    env_ns = os.environ.get("GITLAB_MY_NAMESPACES", "")
    if env_ns:
        return [n.strip() for n in env_ns.split(",") if n.strip()]
    user_md = pathlib.Path.home() / "Memory" / "USER.md"
    if not user_md.exists():
        return []
    match = re.search(r"GITLAB_MY_NAMESPACES:\s*\[([^\]]*)\]", user_md.read_text())
    if not match:
        return []
    return [n.strip().strip("'\"") for n in match.group(1).split(",") if n.strip()]


def get_my_projects() -> list[dict]:
    """List projects in Orsox's namespaces."""
    _require_enabled()
    gl = _get_client()
    namespaces = _load_namespaces()
    projects = []
    try:
        for p in gl.projects.list(membership=True, iterator=True):
            ns = p.namespace.get("full_path", "")
            if not namespaces or any(ns.startswith(n) for n in namespaces):
                projects.append({
                    "id": p.id,
                    "path": p.path_with_namespace,
                    "name": p.name,
                    "last_activity": p.last_activity_at[:10] if p.last_activity_at else "",
                })
    except Exception as e:
        projects.append({"id": 0, "path": f"ERROR: {e}", "name": "", "last_activity": ""})
    return projects


def get_recent_commits(project_path: str, days: int = 1) -> list[dict]:
    """Commits on default branch in the last N days."""
    _require_enabled()
    gl = _get_client()
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).isoformat() + "Z"
    try:
        project = gl.projects.get(project_path)
        commits = project.commits.list(since=since, iterator=True)
        return [
            {
                "sha": c.id[:8],
                "author": c.author_name,
                "message": c.title,
                "time": c.created_at[:16].replace("T", " "),
            }
            for c in commits
        ]
    except Exception as e:
        return [{"sha": "ERR", "author": "", "message": str(e), "time": ""}]


def get_open_mrs(project_path: str) -> list[dict]:
    """Open merge requests for a project."""
    _require_enabled()
    gl = _get_client()
    try:
        project = gl.projects.get(project_path)
        mrs = project.mergerequests.list(state="opened", iterator=True)
        return [
            {
                "iid": mr.iid,
                "title": mr.title,
                "author": mr.author["name"],
                "created": mr.created_at[:10],
                "url": mr.web_url,
            }
            for mr in mrs
        ]
    except Exception as e:
        return [{"iid": 0, "title": str(e), "author": "", "created": "", "url": ""}]


def format_context(days: int = 1) -> str:
    """Summary of recent GitLab activity across Orsox's projects."""
    projects = get_my_projects()
    if not projects:
        return "No GitLab projects found."

    lines = [f"## GitLab — Activity (last {days}d)"]
    for p in projects[:10]:
        commits = get_recent_commits(p["path"], days=days)
        mrs = get_open_mrs(p["path"])
        if not commits and not mrs:
            continue
        lines.append(f"\n### {p['path']}")
        if commits:
            lines.append(f"  Commits ({len(commits)}):")
            for c in commits[:5]:
                lines.append(f"    {c['time']}  {c['author']}: {c['message'][:80]}")
        if mrs:
            lines.append(f"  Open MRs ({len(mrs)}):")
            for mr in mrs[:3]:
                lines.append(f"    !{mr['iid']}  {mr['author']}: {mr['title'][:80]}")
    return "\n".join(lines) if len(lines) > 1 else "No GitLab activity today."
