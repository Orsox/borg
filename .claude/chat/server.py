#!/home/bernd/.claude/venv/bin/python3
"""Second Brain Chat Server — FastAPI + Teams Bot Framework.

Start:
  uvicorn .claude.chat.server:app --host 0.0.0.0 --port 8765

Or via systemd (see .claude/deploy/chat.service).

Endpoints:
  POST /webhook/teams    ← Teams Bot Framework messages
  GET  /health           ← liveness check
  GET  /sessions         ← list active conversations (debug)
  POST /cache/clear      ← force system-prompt reload
"""
import pathlib
import sys

# Resolve paths so imports work from any working directory
_CHAT_DIR = pathlib.Path(__file__).parent          # .claude/chat/
_SCRIPTS_DIR = _CHAT_DIR.parent / "scripts"        # .claude/scripts/
sys.path.insert(0, str(_CHAT_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR))

from dotenv import load_dotenv
load_dotenv(_CHAT_DIR.parents[1] / ".env")         # borg/.env

import os
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from botbuilder.core import TurnContext

from session_store import SessionStore
from claude_client import chat, get_system_prompt, invalidate_cache
from adapters.teams import TeamsAdapter

# ── Sanitization (imported from scripts) ─────────────────────────────────────
try:
    from sanitize import sanitize as _sanitize_fn
    def sanitize(text: str) -> str:
        return _sanitize_fn(text, source="teams")
except ImportError:
    def sanitize(text: str) -> str:  # fallback: basic escaping only
        return text.replace("</external-data>", "[/external-data]")


# ── App + dependencies ────────────────────────────────────────────────────────

app = FastAPI(title="Second Brain", description="Orsox's AI chat interface via Teams")

_store = SessionStore()
_teams = TeamsAdapter()

COMMANDS = {
    "/clear": "Clear conversation history for this thread",
    "/status": "Show second brain status",
    "/help": "Show available commands",
}


# ── Command handling ──────────────────────────────────────────────────────────

def handle_command(cmd: str, conversation_id: str) -> str | None:
    cmd_lower = cmd.strip().lower()

    if cmd_lower == "/clear":
        _store.clear_session(conversation_id)
        return "Conversation history cleared."

    if cmd_lower == "/status":
        try:
            sys.path.insert(0, str(_SCRIPTS_DIR))
            from integrations.registry import status_table
            rows = status_table()
            enabled = [r["name"] for r in rows if r["enabled"]]
            disabled = [r["name"] for r in rows if not r["enabled"]]
            lines = ["**Second Brain Status**"]
            lines.append(f"Enabled: {', '.join(enabled) if enabled else 'none'}")
            if disabled:
                lines.append(f"Not configured: {', '.join(disabled)}")
            return "\n".join(lines)
        except Exception as e:
            return f"Status error: {e}"

    if cmd_lower == "/help":
        lines = ["**Commands:**"]
        for cmd_name, desc in COMMANDS.items():
            lines.append(f"  `{cmd_name}` — {desc}")
        lines.append("\nOr just chat — I know your vault, projects, and team context.")
        return "\n".join(lines)

    return None  # not a command


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@app.post("/webhook/teams")
async def teams_webhook(request: Request):
    if not _teams.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Bot not configured. Set TEAMS_BOT_APP_ID and TEAMS_BOT_APP_PASSWORD in .env",
        )

    body = await request.json()
    auth_header = request.headers.get("Authorization", "")

    async def on_turn(context: TurnContext):
        if not TeamsAdapter.is_message(context):
            return

        raw_text = TeamsAdapter.get_text(context)
        conversation_id = TeamsAdapter.get_conversation_id(context)

        if not raw_text:
            return

        # Handle slash commands without calling Claude
        command_reply = handle_command(raw_text, conversation_id)
        if command_reply is not None:
            await TeamsAdapter.reply(context, command_reply)
            return

        # Sanitize before storing or sending to Claude
        safe_text = sanitize(raw_text)

        # Add to session history
        _store.add_message(conversation_id, "teams", "user", safe_text)
        history = _store.get_history(conversation_id)

        # Call Claude
        try:
            reply_text = chat(history)
        except Exception as e:
            reply_text = f"Error calling Claude: {str(e)[:120]}"

        # Store assistant reply (unsanitized — it's Claude's own output)
        _store.add_message(conversation_id, "teams", "assistant", reply_text)

        # Reply in Teams
        await TeamsAdapter.reply(context, reply_text)

    await _teams.process(body, auth_header, on_turn)
    return Response(status_code=200)


# ── Admin endpoints ───────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "bot": "second-brain",
        "teams_configured": _teams.is_configured,
    }


@app.get("/sessions")
async def sessions():
    return JSONResponse(_store.list_sessions())


@app.post("/cache/clear")
async def clear_cache():
    invalidate_cache()
    return {"status": "cache cleared"}


# ── Dev entrypoint ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")
