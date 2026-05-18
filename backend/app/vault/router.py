"""Vault API — exposes ~/Memory/ data to the BorgOS frontend.

Endpoints:
  GET  /api/vault/drafts                   list active drafts
  GET  /api/vault/drafts/{filename}        read a draft's full content
  POST /api/vault/drafts/{filename}/expire move draft to expired/
  GET  /api/vault/habits                   today's habits status
  GET  /api/vault/search?q=...             RAG search via memory_search.py
  GET  /api/vault/heartbeat                last heartbeat state
"""

import asyncio
import json
import pathlib
import re
import shutil
import sys

from fastapi import APIRouter, HTTPException, Query
from app.auth.router import get_current_user
from fastapi import Depends

router = APIRouter(prefix="/api/vault", tags=["vault"])

VAULT = pathlib.Path.home() / "Memory"
DRAFTS_ACTIVE = VAULT / "drafts" / "active"
DRAFTS_EXPIRED = VAULT / "drafts" / "expired"
HEARTBEAT_STATE = pathlib.Path.home() / ".claude" / "data" / "state" / "heartbeat-state.json"
VENV_PYTHON = pathlib.Path.home() / ".claude" / "venv" / "bin" / "python3"
SEARCH_SCRIPT = pathlib.Path(__file__).parents[3] / ".claude" / "scripts" / "memory_search.py"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_frontmatter(text: str) -> dict:
    """Parse YAML-like frontmatter from a draft file."""
    meta: dict = {}
    if not text.startswith("---"):
        return meta
    end = text.find("\n---", 3)
    if end == -1:
        return meta
    fm = text[3:end].strip()
    for line in fm.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta


def _content_after_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + 4:].strip()


# ── Draft endpoints ────────────────────────────────────────────────────────────

@router.get("/drafts")
async def list_drafts(_user=Depends(get_current_user)):
    """List all files in ~/Memory/drafts/active/."""
    if not DRAFTS_ACTIVE.exists():
        return []

    drafts = []
    for f in sorted(DRAFTS_ACTIVE.glob("*.md"), reverse=True):
        try:
            text = await asyncio.to_thread(f.read_text, encoding="utf-8")
        except OSError:
            continue
        meta = _parse_frontmatter(text)
        content = _content_after_frontmatter(text)
        drafts.append({
            "filename": f.name,
            "type": meta.get("type", "general"),
            "source_id": meta.get("source_id", ""),
            "subject": meta.get("subject", f.stem),
            "created": meta.get("created", ""),
            "status": meta.get("status", "active"),
            "content_preview": content[:200].strip(),
        })
    return drafts


@router.get("/drafts/{filename}")
async def get_draft(filename: str, _user=Depends(get_current_user)):
    """Return full content of a specific draft."""
    # Sanitize: only allow filenames, no path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = DRAFTS_ACTIVE / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Draft not found")
    content = await asyncio.to_thread(path.read_text, encoding="utf-8")
    return {"filename": filename, "content": content}


@router.post("/drafts/{filename}/expire")
async def expire_draft(filename: str, _user=Depends(get_current_user)):
    """Move a draft from active/ to expired/."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    src = DRAFTS_ACTIVE / filename
    if not src.exists():
        raise HTTPException(status_code=404, detail="Draft not found")

    DRAFTS_EXPIRED.mkdir(parents=True, exist_ok=True)
    dst = DRAFTS_EXPIRED / filename
    await asyncio.to_thread(shutil.move, str(src), str(dst))
    return {"ok": True, "moved_to": str(dst)}


# ── Habits endpoint ────────────────────────────────────────────────────────────

@router.get("/habits")
async def get_habits(_user=Depends(get_current_user)):
    """Parse today's HABITS.md checklist and return pillar status."""
    habits_file = VAULT / "HABITS.md"
    if not habits_file.exists():
        return []

    text = await asyncio.to_thread(habits_file.read_text, encoding="utf-8")
    habits = []
    in_today = False

    for line in text.splitlines():
        if re.match(r"^## Today", line):
            in_today = True
            continue
        if re.match(r"^## ", line) and in_today:
            break
        if not in_today:
            continue

        checked_match = re.match(r"- \[([ x])\] \*\*(.+?)\*\*(.*)", line)
        if checked_match:
            checked = checked_match.group(1) == "x"
            pillar = checked_match.group(2).strip()
            desc = checked_match.group(3).strip().lstrip("—").strip()
            # Auto-detectable pillars (from HABITS.md auto-detection rules)
            auto = pillar.lower() in ("agent shipping", "ai learning")
            habits.append({
                "pillar": pillar,
                "description": desc,
                "checked": checked,
                "auto_detectable": auto,
            })

    return habits


# ── Search endpoint ────────────────────────────────────────────────────────────

@router.get("/search")
async def search_vault(
    q: str = Query(..., min_length=1),
    top_k: int = Query(default=5, ge=1, le=20),
    _user=Depends(get_current_user),
):
    """Hybrid RAG search via memory_search.py subprocess."""
    if not SEARCH_SCRIPT.exists():
        raise HTTPException(status_code=503, detail="Search script not available")
    if not VENV_PYTHON.exists():
        raise HTTPException(status_code=503, detail="Venv Python not found")

    try:
        proc = await asyncio.create_subprocess_exec(
            str(VENV_PYTHON), str(SEARCH_SCRIPT),
            q, "--top-k", str(top_k), "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)
        results = json.loads(stdout.decode())
        return [
            {
                "path": r.get("path", ""),
                "content": r.get("content", "")[:300],
                "score": r.get("hybrid_score", 0),
            }
            for r in results
        ]
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Search timed out")
    except (json.JSONDecodeError, Exception) as e:
        raise HTTPException(status_code=500, detail=f"Search error: {e}")


# ── Heartbeat status ───────────────────────────────────────────────────────────

@router.get("/heartbeat")
async def get_heartbeat_status(_user=Depends(get_current_user)):
    """Return the last heartbeat state snapshot."""
    if not HEARTBEAT_STATE.exists():
        raise HTTPException(status_code=404, detail="No heartbeat state found")

    try:
        text = await asyncio.to_thread(HEARTBEAT_STATE.read_text, encoding="utf-8")
        state = json.loads(text)
        return {
            "timestamp": state.get("timestamp", ""),
            "jira_count": len(state.get("jira", [])),
            "gitlab_projects": list(state.get("gitlab", {}).keys()),
            "teams_count": len(state.get("teams", [])),
            "polarion_count": len(state.get("polarion", [])),
        }
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=500, detail=f"State read error: {e}")


# ── Graph endpoints ────────────────────────────────────────────────────────────

from .scanner import scan_vault
from .graph import build_vault_graph
from .schemas import VaultGraph


@router.get("/graph", response_model=VaultGraph, summary="Get vault knowledge graph")
async def get_vault_graph(_user=Depends(get_current_user)) -> VaultGraph:
    """Return the vault's markdown notes and wiki-link relationships as a graph."""
    def _build() -> VaultGraph:
        if not VAULT.exists():
            raise HTTPException(status_code=404, detail=f"Vault not found at {VAULT}")
        return build_vault_graph(scan_vault(VAULT))

    return await asyncio.to_thread(_build)


@router.get("/file", summary="Read a vault markdown file")
async def get_vault_file(
    path: str = Query(..., min_length=1),
    _user=Depends(get_current_user),
) -> dict:
    """Return the raw content of a .md file inside the vault."""
    # Sanitize: reject path traversal
    if ".." in path or path.startswith("/") or "\\" in path:
        raise HTTPException(status_code=400, detail="Invalid path")

    full = (VAULT / path).resolve()
    vault_resolved = VAULT.resolve()

    # Ensure resolved path is under the vault root
    if vault_resolved not in full.parents and full != vault_resolved:
        raise HTTPException(status_code=400, detail="Path outside vault")

    if not full.exists() or not full.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    if full.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="Only .md files are served")

    content = await asyncio.to_thread(full.read_text, encoding="utf-8")
    return {"path": path, "content": content}
