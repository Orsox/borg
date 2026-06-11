"""API router for Second Brain module."""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.second_brain import action_service, service
from app.second_brain.schemas import (
    BacklinkItem,
    CombinedGraph,
    CombinedGraphEdge,
    CombinedGraphNode,
    FederatedSearchResponse,
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    NoteCreate,
    NoteListItem,
    NoteResponse,
    NoteUpdate,
    PaginatedNotes,
)
from app.second_brain.search import VALID_SOURCES, federated_search
from app.auth.router import get_current_user
from app.database import get_session

router = APIRouter(prefix="/api/brain", tags=["second_brain"])


@router.post("/notes", response_model=NoteResponse, status_code=201)
async def create_note(
    body: NoteCreate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    note = await service.create_note(
        db,
        title=body.title,
        content=body.content,
        tags=body.tags,
    )
    return NoteResponse(
        id=note.id,
        title=note.title,
        content=note.content,
        tags=json.loads(note.tags) if note.tags else [],
        is_archived=note.is_archived,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.get("/notes", response_model=PaginatedNotes)
async def list_notes(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    tags: str | None = Query(default=None),
    archived: bool = Query(default=False),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    import json
    result = await service.list_notes(
        db,
        page=page,
        size=size,
        search=search,
        tags=tags,
        archived=archived,
    )
    return PaginatedNotes(
        items=[
            NoteListItem(
                id=n.id,
                title=n.title,
                tags=json.loads(n.tags) if n.tags else [],
                created_at=n.created_at,
                updated_at=n.updated_at,
            )
            for n in result["items"]
        ],
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
    )


@router.get("/notes/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    import json
    note = await service.get_note(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    return NoteResponse(
        id=note.id,
        title=note.title,
        content=note.content,
        tags=json.loads(note.tags) if note.tags else [],
        is_archived=note.is_archived,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.put("/notes/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: int,
    body: NoteUpdate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    import json
    note = await service.update_note(
        db,
        note_id=note_id,
        title=body.title,
        content=body.content,
        tags=body.tags,
    )
    if not note:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    return NoteResponse(
        id=note.id,
        title=note.title,
        content=note.content,
        tags=json.loads(note.tags) if note.tags else [],
        is_archived=note.is_archived,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.delete("/notes/{note_id}", response_model=NoteResponse)
async def archive_note(
    note_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    import json
    note = await service.archive_note(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    return NoteResponse(
        id=note.id,
        title=note.title,
        content=note.content,
        tags=json.loads(note.tags) if note.tags else [],
        is_archived=note.is_archived,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.get("/notes/{note_id}/backlinks", response_model=list[BacklinkItem])
async def get_backlinks(
    note_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    note = await service.get_note(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    backlinks = await service.get_backlinks(db, note_id)
    return [BacklinkItem(id=b.id, title=b.title, updated_at=b.updated_at) for b in backlinks]


@router.get("/search", response_model=FederatedSearchResponse)
async def search_brain(
    q: str = Query(default=""),
    sources: str = Query(default="note,vault,action"),
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """One search box across DB notes, the Obsidian vault, and action memory.

    Result IDs are namespaced ("note:", "vault:", "action:") like the
    combined graph, so a hit from any source opens in the same detail view.
    An empty q is browse mode: all items from the selected sources, newest
    first — this feeds the workspace item list.
    """
    requested = {s.strip().lower() for s in sources.split(",") if s.strip()}
    selected = requested & VALID_SOURCES
    if not selected:
        raise HTTPException(
            status_code=400,
            detail=f"sources must include at least one of: {', '.join(sorted(VALID_SOURCES))}",
        )

    results = await federated_search(db, q, selected, limit=limit)
    return FederatedSearchResponse(
        query=q,
        sources=sorted(selected),
        results=results,
    )


@router.get("/graph", response_model=KnowledgeGraph)
async def get_knowledge_graph(
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    graph = await service.get_knowledge_graph(db)
    return KnowledgeGraph(
        nodes=[GraphNode(**n) for n in graph["nodes"]],
        edges=[GraphEdge(**e) for e in graph["edges"]],
    )


@router.get("/graph/combined", response_model=CombinedGraph)
async def get_combined_graph(
    link_tags: bool = Query(default=False),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """Unified graph merging the Obsidian vault, DB notes, and action memory.

    Node IDs are namespaced ("vault:", "note:", "action:") so the three
    sources never collide. Set link_tags=true to add bridge edges between
    nodes of different sources that share a tag.
    """
    from app.vault.graph import build_vault_graph
    from app.vault.router import VAULT
    from app.vault.scanner import scan_vault

    nodes: list[CombinedGraphNode] = []
    edges: list[CombinedGraphEdge] = []

    # ── Vault (filesystem markdown) ──────────────────────────────────────────
    if VAULT.exists():
        vault_graph = await asyncio.to_thread(
            lambda: build_vault_graph(scan_vault(VAULT))
        )
        for n in vault_graph.nodes:
            nodes.append(CombinedGraphNode(
                id=f"vault:{n.id}",
                title=n.title,
                source="vault",
                kind=n.kind.value,
                tags=n.tags,
                backlink_count=n.backlink_count,
                ref=n.rel_path,
            ))
        for e in vault_graph.edges:
            edges.append(CombinedGraphEdge(
                source=f"vault:{e.source}",
                target=f"vault:{e.target}",
            ))

    # ── DB notes ─────────────────────────────────────────────────────────────
    kg = await service.get_knowledge_graph(db)
    for n in kg["nodes"]:
        nodes.append(CombinedGraphNode(
            id=f"note:{n['id']}",
            title=n["title"],
            source="note",
            kind="db-note",
            tags=n["tags"],
            backlink_count=0,
            ref=str(n["id"]),
        ))
    for e in kg["edges"]:
        edges.append(CombinedGraphEdge(
            source=f"note:{e['source']}",
            target=f"note:{e['target']}",
        ))

    # ── Action memory ────────────────────────────────────────────────────────
    actions = await action_service.list_action_memories(
        db, page=1, size=100, archived=False
    )
    for a in actions["items"]:
        nodes.append(CombinedGraphNode(
            id=f"action:{a.id}",
            title=a.title,
            source="action",
            kind=a.status,
            tags=action_service._json_to_tags(a.tags),
            backlink_count=0,
            ref=str(a.id),
        ))

    # ── Optional tag bridges ─────────────────────────────────────────────────
    # Connect nodes that share a tag so otherwise-isolated clusters (e.g. all
    # "timeout" failures, or one workflow's runs) become visible. Hub tags that
    # span too many nodes are skipped to avoid a dense, unreadable clique.
    if link_tags:
        from collections import defaultdict

        MAX_TAG_FANOUT = 10

        tag_index: dict[str, list[CombinedGraphNode]] = defaultdict(list)
        for n in nodes:
            for tag in n.tags:
                tag_index[tag.lower()].append(n)

        # Avoid duplicating edges that already exist (wiki-links, note links).
        seen: set[tuple[str, str]] = {
            tuple(sorted((e.source, e.target))) for e in edges
        }
        for members in tag_index.values():
            if len(members) < 2 or len(members) > MAX_TAG_FANOUT:
                continue
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    key = tuple(sorted((members[i].id, members[j].id)))
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append(CombinedGraphEdge(source=key[0], target=key[1]))

    return CombinedGraph(nodes=nodes, edges=edges)
