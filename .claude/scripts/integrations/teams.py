"""Microsoft Teams integration — read messages and @mentions via Microsoft Graph.

Auth: Device Code Flow (interactive first run, then token cached)
  1. Register an app in Azure Portal → Microsoft Entra ID → App registrations
  2. Add API permissions: Chat.Read, ChannelMessage.Read.All (needs admin consent)
  3. Set AZURE_CLIENT_ID and AZURE_TENANT_ID in borg/.env
  4. Run: query.py teams --auth   (opens browser on first use)

Token cached at: ~/.cache/second-brain/msal-token.json
"""
import os
import json
import asyncio
import pathlib
import datetime

import msal

from .registry import is_enabled

_CACHE_FILE = pathlib.Path.home() / ".cache" / "second-brain" / "msal-token.json"
_SCOPES = ["Chat.Read", "ChannelMessage.Read.All", "User.Read"]


def _require_enabled():
    if not is_enabled("teams"):
        raise RuntimeError("Teams not configured. Add AZURE_CLIENT_ID and AZURE_TENANT_ID to .env")


def _get_msal_app() -> tuple[msal.PublicClientApplication, msal.SerializableTokenCache]:
    cache = msal.SerializableTokenCache()
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _CACHE_FILE.exists():
        cache.deserialize(_CACHE_FILE.read_text())

    app = msal.PublicClientApplication(
        client_id=os.environ["AZURE_CLIENT_ID"],
        authority=f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}",
        token_cache=cache,
    )
    return app, cache


def _save_cache(cache: msal.SerializableTokenCache):
    if cache.has_state_changed:
        _CACHE_FILE.write_text(cache.serialize())


def authenticate() -> str:
    """Interactive device code auth. Run once; token cached afterward."""
    _require_enabled()
    app, cache = _get_msal_app()

    flow = app.initiate_device_flow(scopes=_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device flow failed: {flow.get('error_description')}")

    print(flow["message"])  # prints the URL + code for the user
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"Auth failed: {result.get('error_description')}")
    _save_cache(cache)
    print("Teams auth successful — token cached.")
    return result["access_token"]


def _get_token() -> str | None:
    """Return a cached access token, or None if not authenticated."""
    if not is_enabled("teams"):
        return None
    app, cache = _get_msal_app()
    accounts = app.get_accounts()
    if not accounts:
        return None
    result = app.acquire_token_silent(_SCOPES, account=accounts[0])
    if result and "access_token" in result:
        _save_cache(cache)
        return result["access_token"]
    return None


async def _get_graph_client():
    from azure.identity.aio import OnBehalfOfCredential
    from msgraph import GraphServiceClient
    token = _get_token()
    if not token:
        raise RuntimeError(
            "Teams not authenticated. Run: query.py teams --auth"
        )
    # Use the cached token directly via a simple credential wrapper
    from azure.core.credentials import AccessToken
    import time

    class _StaticCredential:
        async def get_token(self, *args, **kwargs):
            return AccessToken(token, int(time.time()) + 3600)
        async def close(self): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    return GraphServiceClient(credentials=_StaticCredential(), scopes=_SCOPES)


async def _get_recent_mentions_async(hours: int = 24) -> list[dict]:
    client = await _get_graph_client()
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)

    mentions = []
    try:
        chats = await client.me.chats.get()
        if chats and chats.value:
            for chat in chats.value[:20]:  # cap to 20 chats
                msgs = await client.me.chats.by_chat_id(chat.id).messages.get()
                if not msgs or not msgs.value:
                    continue
                for msg in msgs.value:
                    if not msg.created_date_time:
                        continue
                    if msg.created_date_time.replace(tzinfo=None) < cutoff:
                        continue
                    body = (msg.body.content or "") if msg.body else ""
                    if "orsox" in body.lower() or "@" in body:
                        mentions.append({
                            "chat_id": chat.id,
                            "sender": str(getattr(msg.from_, "user", {}).get("displayName", "Unknown")) if msg.from_ else "Unknown",
                            "body": body[:300].strip(),
                            "time": str(msg.created_date_time)[:16],
                        })
    except Exception as e:
        mentions.append({"chat_id": "", "sender": "ERROR", "body": str(e), "time": ""})

    return mentions


def get_recent_mentions(hours: int = 24) -> list[dict]:
    _require_enabled()
    return asyncio.run(_get_recent_mentions_async(hours=hours))


def format_context(hours: int = 24) -> str:
    try:
        mentions = get_recent_mentions(hours=hours)
    except RuntimeError as e:
        return f"## Teams\n  {e}"

    if not mentions:
        return f"No Teams mentions in the last {hours}h."

    lines = [f"## Teams — Mentions ({len(mentions)}, last {hours}h)"]
    for m in mentions:
        lines.append(f"\n  {m['time']}  From: {m['sender']}")
        lines.append(f"  {m['body'][:200]}")
    return "\n".join(lines)
