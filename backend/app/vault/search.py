"""Lightweight substring search over vault markdown files (title, tags, content).

Unlike /api/vault/search (hybrid RAG via an external subprocess), this scanner
has no dependencies beyond the vault itself, so the federated brain search can
always include vault results.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import frontmatter

from .graph import classify
from .scanner import EXCLUDED_DIRS, parse_note_file

logger = logging.getLogger(__name__)

SNIPPET_RADIUS = 80

# Match scores shared by all federated-search sources.
SCORE_TITLE = 3
SCORE_TAG = 2
SCORE_CONTENT = 1


def make_snippet(content: str, query: str) -> str:
    """Return a short excerpt of content centered on the first query match."""
    content = content.strip()
    idx = content.lower().find(query.lower())
    if idx == -1:
        return content[: SNIPPET_RADIUS * 2].strip()
    start = max(0, idx - SNIPPET_RADIUS)
    end = min(len(content), idx + len(query) + SNIPPET_RADIUS)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    return f"{prefix}{content[start:end].strip()}{suffix}"


@dataclass(frozen=True)
class VaultSearchHit:
    rel_path: str
    title: str
    kind: str
    tags: list[str]
    snippet: str
    score: int
    mtime: datetime


def search_vault_files(vault_path: Path, query: str, limit: int = 20) -> list[VaultSearchHit]:
    """Scan all vault .md files and match query against title, tags, and content.

    An empty query is browse mode: every note matches with score 0 and the
    result is ordered by file mtime (newest first) instead of match quality.
    """
    q = query.strip().lower()
    if not vault_path.is_dir():
        return []

    hits: list[VaultSearchHit] = []
    for file_path in vault_path.rglob("*.md"):
        if any(part in EXCLUDED_DIRS for part in file_path.parts):
            continue
        parsed = parse_note_file(file_path, vault_root=vault_path)
        if parsed is None:
            continue
        try:
            content = frontmatter.load(file_path).content
        except Exception:
            content = ""

        if not q:
            score = 0
        elif q in parsed.title.lower():
            score = SCORE_TITLE
        elif any(q in t.lower() for t in parsed.tags):
            score = SCORE_TAG
        elif q in content.lower():
            score = SCORE_CONTENT
        else:
            continue

        try:
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            mtime = datetime.fromtimestamp(0, tz=timezone.utc)

        hits.append(VaultSearchHit(
            rel_path=parsed.rel_path,
            title=parsed.title,
            kind=classify(parsed).value,
            tags=parsed.tags,
            snippet=make_snippet(content, q) if q else content[:160].strip(),
            score=score,
            mtime=mtime,
        ))

    if q:
        hits.sort(key=lambda h: (-h.score, h.title.lower()))
    else:
        hits.sort(key=lambda h: h.mtime, reverse=True)
    return hits[:limit]
