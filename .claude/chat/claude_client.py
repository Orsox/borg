"""Claude (Anthropic API) wrapper for the chat interface.

Builds a system prompt from the vault and handles conversation turns.
System prompt is cached for 5 minutes to avoid re-reading files on every message.
"""
import datetime
import os
import pathlib
import sys

VAULT = pathlib.Path.home() / "Memory"
MAX_TOKENS = 1500
CACHE_TTL_SECONDS = 300  # 5 min

_cached_prompt: str | None = None
_cache_time: datetime.datetime | None = None


def build_system_prompt() -> str:
    """Build system prompt from SOUL.md + MEMORY.md + chat-specific instructions."""
    parts = []

    for fname in ["SOUL.md", "MEMORY.md"]:
        p = VAULT / fname
        if p.exists():
            parts.append(f"=== {fname} ===\n{p.read_text().strip()}")

    parts.append("""=== Chat Interface Instructions ===
You are responding to Orsox directly in their Teams DM with the Second Brain bot.

Guidelines:
- Be concise: prefer 3-5 bullets or 2-3 sentences over long prose.
- You have access to Orsox's vault context above. Reference it when relevant.
- When asked to search the vault, note you can do so with: msearch "<query>"
- When asked about Jira/GitLab/Polarion, note Orsox can run: q <integration> <cmd>
- Creating a draft? Tell Orsox the filename in drafts/active/ so they can find it.
- You are NOT connected to live integrations in this chat — for live data, use the CLI tools.
- ADVISOR mode: you suggest, Orsox acts. Never claim to have sent or posted anything.""")

    return "\n\n".join(parts)


def get_system_prompt() -> str:
    """Return cached system prompt, refreshing if older than TTL."""
    global _cached_prompt, _cache_time
    now = datetime.datetime.now()
    if (
        _cached_prompt is None
        or _cache_time is None
        or (now - _cache_time).total_seconds() > CACHE_TTL_SECONDS
    ):
        _cached_prompt = build_system_prompt()
        _cache_time = now
    return _cached_prompt


def chat(history: list[dict]) -> str:
    """Send conversation history to Claude and return the assistant's reply."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "Error: ANTHROPIC_API_KEY not configured."

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=MAX_TOKENS,
        system=get_system_prompt(),
        messages=history,
    )
    return msg.content[0].text


def invalidate_cache():
    """Force system prompt reload on next request (call after vault edits)."""
    global _cached_prompt, _cache_time
    _cached_prompt = None
    _cache_time = None
