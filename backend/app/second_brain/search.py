"""Federated search across DB notes, the Obsidian vault, and action memory.

Results from every source share one shape (SearchResultItem) with namespaced
IDs ("note:", "vault:", "action:") matching the combined graph, so the
frontend can route a hit from any source to the same detail view.
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.second_brain import action_service, service
from app.second_brain.schemas import SearchResultItem
from app.vault.search import SCORE_CONTENT, SCORE_TAG, SCORE_TITLE, make_snippet

VALID_SOURCES = {"note", "vault", "action"}


def _score(query: str, title: str, tags: list[str]) -> int:
    if not query:
        return 0
    q = query.lower()
    if q in title.lower():
        return SCORE_TITLE
    if any(q in t.lower() for t in tags):
        return SCORE_TAG
    return SCORE_CONTENT


def _ts(dt: datetime | None) -> float:
    """Sortable timestamp; DB datetimes are naive UTC, vault mtimes are aware."""
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


async def _search_notes(db: AsyncSession, query: str, limit: int) -> list[SearchResultItem]:
    result = await service.list_notes(db, page=1, size=limit, search=query or None)
    items = []
    for n in result["items"]:
        tags = service._json_to_tags(n.tags)
        items.append(SearchResultItem(
            id=f"note:{n.id}",
            title=n.title,
            source="note",
            kind="db-note",
            tags=tags,
            ref=str(n.id),
            snippet=make_snippet(n.content, query) if query else n.content[:160].strip(),
            score=_score(query, n.title, tags),
            updated_at=n.updated_at,
        ))
    return items


async def _search_actions(db: AsyncSession, query: str, limit: int) -> list[SearchResultItem]:
    result = await action_service.list_action_memories(
        db, page=1, size=limit, search=query or None, archived=False
    )
    items = []
    for a in result["items"]:
        tags = action_service._json_to_tags(a.tags)
        description = a.description or ""
        items.append(SearchResultItem(
            id=f"action:{a.id}",
            title=a.title,
            source="action",
            kind=a.status,
            tags=tags,
            ref=str(a.id),
            snippet=make_snippet(description, query) if query else description[:160].strip(),
            score=_score(query, a.title, tags),
            updated_at=a.updated_at,
        ))
    return items


async def _search_vault(query: str, limit: int) -> list[SearchResultItem]:
    from app.vault.router import VAULT
    from app.vault.search import search_vault_files

    hits = await asyncio.to_thread(search_vault_files, VAULT, query, limit)
    return [
        SearchResultItem(
            id=f"vault:{h.rel_path}",
            title=h.title,
            source="vault",
            kind=h.kind,
            tags=h.tags,
            ref=h.rel_path,
            snippet=h.snippet,
            score=h.score,
            updated_at=h.mtime,
        )
        for h in hits
    ]


async def federated_search(
    db: AsyncSession,
    query: str,
    sources: set[str],
    limit: int = 20,
) -> list[SearchResultItem]:
    """Fan out to the requested sources and merge.

    With a query, results are ordered by match quality; an empty query is
    browse mode and orders by updated_at (newest first). The vault scan runs
    in a thread alongside the DB queries; the two DB searches stay sequential
    because they share one AsyncSession.
    """
    vault_task = (
        asyncio.create_task(_search_vault(query, limit)) if "vault" in sources else None
    )

    results: list[SearchResultItem] = []
    if "note" in sources:
        results.extend(await _search_notes(db, query, limit))
    if "action" in sources:
        results.extend(await _search_actions(db, query, limit))
    if vault_task is not None:
        results.extend(await vault_task)

    if query.strip():
        results.sort(key=lambda r: (-r.score, r.title.lower()))
    else:
        results.sort(key=lambda r: _ts(r.updated_at), reverse=True)
    return results[:limit]
