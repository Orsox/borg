"""OneDrive integration — list and search files via Microsoft Graph.

Shares Azure auth with Teams integration (same app registration + token cache).
Run `query.py teams --auth` once to authenticate both.

Set AZURE_CLIENT_ID and AZURE_TENANT_ID in borg/.env.
"""
import asyncio
import datetime

from .registry import is_enabled
from .teams import _get_token, _get_graph_client


def _require_enabled():
    if not is_enabled("onedrive"):
        raise RuntimeError("OneDrive not configured. Add AZURE_CLIENT_ID and AZURE_TENANT_ID to .env")


async def _list_recent_async(days: int = 3) -> list[dict]:
    client = await _get_graph_client()
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        result = await client.me.drive.root.children.get()
        files = []
        if result and result.value:
            for item in result.value:
                if not item.last_modified_date_time:
                    continue
                mtime_str = str(item.last_modified_date_time)[:16]
                files.append({
                    "name": item.name,
                    "path": f"/drives/me/root/{item.name}",
                    "modified": mtime_str,
                    "size_kb": round((item.size or 0) / 1024, 1),
                    "url": getattr(item, "web_url", ""),
                })
        return sorted(files, key=lambda x: x["modified"], reverse=True)
    except Exception as e:
        return [{"name": f"ERROR: {e}", "path": "", "modified": "", "size_kb": 0, "url": ""}]


async def _search_async(query: str) -> list[dict]:
    client = await _get_graph_client()
    try:
        result = await client.me.drive.root.search_with_q(q=query).get()
        if not result or not result.value:
            return []
        return [
            {
                "name": item.name,
                "path": f"/drives/me/root/{item.parent_reference.path if item.parent_reference else ''}/{item.name}",
                "modified": str(item.last_modified_date_time)[:10] if item.last_modified_date_time else "",
                "url": getattr(item, "web_url", ""),
            }
            for item in result.value[:20]
        ]
    except Exception as e:
        return [{"name": f"ERROR: {e}", "path": "", "modified": "", "url": ""}]


def list_recent(days: int = 3) -> list[dict]:
    _require_enabled()
    token = _get_token()
    if not token:
        raise RuntimeError("OneDrive not authenticated. Run: query.py teams --auth")
    return asyncio.run(_list_recent_async(days=days))


def search_files(query: str) -> list[dict]:
    _require_enabled()
    token = _get_token()
    if not token:
        raise RuntimeError("OneDrive not authenticated. Run: query.py teams --auth")
    return asyncio.run(_search_async(query))


def format_context(days: int = 3) -> str:
    try:
        files = list_recent(days=days)
    except RuntimeError as e:
        return f"## OneDrive\n  {e}"

    if not files:
        return f"No OneDrive changes in the last {days} days."

    lines = [f"## OneDrive — Recent Files (last {days}d)"]
    for f in files[:10]:
        lines.append(f"  {f['modified']}  {f['name']}  ({f['size_kb']}KB)")
    return "\n".join(lines)
