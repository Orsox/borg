"""Federated search across DB notes, the Obsidian vault, and action memory.

Results from every source share one shape (SearchResultItem) with namespaced
IDs ("note:", "vault:", "action:") matching the combined graph, so the
frontend can route a hit from any source to the same detail view.
"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.second_brain import action_service, service
from app.second_brain.schemas import SearchResultItem
from app.vault.search import SCORE_CONTENT, SCORE_TAG, SCORE_TITLE, make_snippet

VALID_SOURCES = {"note", "vault", "action"}


def _score(query: str, title: str, tags: list[str]) -> int:
    q = query.lower()
    if q in title.lower():
        return SCORE_TITLE
    if any(q in t.lower() for t in tags):
        return SCORE_TAG
    return SCORE_CONTENT


async def _search_notes(db: AsyncSession, query: str, limit: int) -> list[SearchResultItem]:
    result = await service.list_notes(db, page=1, size=limit, search=query)
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
            snippet=make_snippet(n.content, query),
            score=_score(query, n.title, tags),
        ))
    return items


async def _search_actions(db: AsyncSession, query: str, limit: int) -> list[SearchResultItem]:
    result = await action_service.list_action_memories(
        db, page=1, size=limit, search=query, archived=False
    )
    items = []
    for a in result["items"]:
        tags = action_service._json_to_tags(a.tags)
        items.append(SearchResultItem(
            id=f"action:{a.id}",
            title=a.title,
            source="action",
            kind=a.status,
            tags=tags,
            ref=str(a.id),
            snippet=make_snippet(a.description or "", query),
            score=_score(query, a.title, tags),
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
        )
        for h in hits
    ]


async def federated_search(
    db: AsyncSession,
    query: str,
    sources: set[str],
    limit: int = 20,
) -> list[SearchResultItem]:
    """Fan out to the requested sources and merge by score.

    The vault scan runs in a thread alongside the DB queries; the two DB
    searches stay sequential because they share one AsyncSession.
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

    results.sort(key=lambda r: (-r.score, r.title.lower()))
    return results[:limit]
