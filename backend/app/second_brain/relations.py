"""Cross-source relations for the Second Brain.

Builds the combined knowledge graph (vault + DB notes + action memory) and
answers per-item relation queries (links, backlinks, tag-related items).

Cross-source wiki-links are resolved here at read time, so they are always
fresh and the read-only vault never needs DB rows:
  - a [[target]] in a DB note that matches no DB note falls back to vault
    titles/paths → "note:X → vault:rel/path.md" edge
  - a [[target]] in a vault file that dangles inside the vault falls back to
    DB note titles → "vault:rel/path.md → note:X" edge
"""

import asyncio
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.second_brain import action_service, service
from app.second_brain.graph import parse_wiki_links
from app.second_brain.models import Note, NoteLink
from app.second_brain.schemas import (
    CombinedGraph,
    CombinedGraphEdge,
    CombinedGraphNode,
    ItemRelations,
    RelatedItem,
)

MAX_TAG_FANOUT = 10
MAX_RELATED = 15


async def build_combined_graph(db: AsyncSession, link_tags: bool = False) -> CombinedGraph:
    """Unified graph merging the Obsidian vault, DB notes, and action memory.

    Node IDs are namespaced ("vault:", "note:", "action:") so the three
    sources never collide. Wiki-links across sources become real edges; set
    link_tags=True to additionally bridge nodes of different sources that
    share a tag.
    """
    from app.vault.graph import build_vault_graph, resolve_link
    from app.vault.router import VAULT
    from app.vault.scanner import scan_vault

    nodes: list[CombinedGraphNode] = []
    edges: list[CombinedGraphEdge] = []
    edge_seen: set[tuple[str, str]] = set()

    def add_edge(source: str, target: str) -> None:
        key = tuple(sorted((source, target)))
        if key in edge_seen:
            return
        edge_seen.add(key)
        edges.append(CombinedGraphEdge(source=source, target=target))

    # ── Vault (filesystem markdown) ──────────────────────────────────────────
    vault_notes = []
    vault_by_title: dict[str, str] = {}    # title (lower) → rel_path
    vault_by_relpath: dict[str, str] = {}  # rel_path (with/without .md) → rel_path
    if VAULT.exists():
        def _scan_and_build():
            parsed = scan_vault(VAULT)
            return parsed, build_vault_graph(parsed)

        vault_notes, vault_graph = await asyncio.to_thread(_scan_and_build)
        for vn in vault_notes:
            vault_by_title[vn.title.lower()] = vn.rel_path
            vault_by_relpath[vn.rel_path] = vn.rel_path
            vault_by_relpath.setdefault(vn.rel_path.removesuffix(".md"), vn.rel_path)
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
            add_edge(f"vault:{e.source}", f"vault:{e.target}")

    # ── DB notes ─────────────────────────────────────────────────────────────
    notes_result = await db.execute(select(Note).where(Note.is_archived == False))  # noqa: E712
    db_notes = list(notes_result.scalars().all())
    note_by_title: dict[str, int] = {n.title.lower(): n.id for n in db_notes}

    for n in db_notes:
        nodes.append(CombinedGraphNode(
            id=f"note:{n.id}",
            title=n.title,
            source="note",
            kind="db-note",
            tags=service._json_to_tags(n.tags),
            backlink_count=0,
            ref=str(n.id),
        ))

    links_result = await db.execute(
        select(NoteLink).join(Note, Note.id == NoteLink.source_id).where(Note.is_archived == False)  # noqa: E712
    )
    for link in links_result.scalars().all():
        add_edge(f"note:{link.source_id}", f"note:{link.target_id}")

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

    # ── Cross-source wiki-links ──────────────────────────────────────────────
    # DB note → vault: targets that no DB note title satisfies.
    for n in db_notes:
        for target in parse_wiki_links(n.content or ""):
            if target.strip().lower() in note_by_title:
                continue  # already covered by note_links
            resolved = resolve_link(target, vault_by_title, vault_by_relpath)
            if resolved:
                add_edge(f"note:{n.id}", f"vault:{resolved}")

    # Vault → DB note: targets dangling inside the vault.
    for vn in vault_notes:
        for target in vn.wiki_targets:
            if resolve_link(target, vault_by_title, vault_by_relpath):
                continue  # resolves inside the vault
            note_id = note_by_title.get(target.strip().lower())
            if note_id is not None:
                add_edge(f"vault:{vn.rel_path}", f"note:{note_id}")

    # ── Optional tag bridges ─────────────────────────────────────────────────
    # Connect nodes that share a tag so otherwise-isolated clusters (e.g. all
    # "timeout" failures, or one workflow's runs) become visible. Hub tags that
    # span too many nodes are skipped to avoid a dense, unreadable clique.
    if link_tags:
        tag_index: dict[str, list[CombinedGraphNode]] = defaultdict(list)
        for n in nodes:
            for tag in n.tags:
                tag_index[tag.lower()].append(n)

        for members in tag_index.values():
            if len(members) < 2 or len(members) > MAX_TAG_FANOUT:
                continue
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    add_edge(members[i].id, members[j].id)

    return CombinedGraph(nodes=nodes, edges=edges)


def _as_related(n: CombinedGraphNode) -> RelatedItem:
    return RelatedItem(
        id=n.id, title=n.title, source=n.source, kind=n.kind, tags=n.tags, ref=n.ref
    )


async def get_item_relations(db: AsyncSession, item_id: str) -> ItemRelations | None:
    """Links, backlinks, and tag-related items for one namespaced item id."""
    graph = await build_combined_graph(db, link_tags=False)
    node_map = {n.id: n for n in graph.nodes}
    me = node_map.get(item_id)
    if me is None:
        return None

    links: list[CombinedGraphNode] = []
    backlinks: list[CombinedGraphNode] = []
    for e in graph.edges:
        if e.source == item_id and e.target in node_map:
            links.append(node_map[e.target])
        elif e.target == item_id and e.source in node_map:
            backlinks.append(node_map[e.source])

    # Tag overlap, strongest first; items already linked are not repeated.
    my_tags = {t.lower() for t in me.tags}
    related: list[CombinedGraphNode] = []
    if my_tags:
        connected = {item_id} | {n.id for n in links} | {n.id for n in backlinks}
        scored: list[tuple[int, CombinedGraphNode]] = []
        for n in graph.nodes:
            if n.id in connected:
                continue
            overlap = len(my_tags & {t.lower() for t in n.tags})
            if overlap:
                scored.append((overlap, n))
        scored.sort(key=lambda x: (-x[0], x[1].title.lower()))
        related = [n for _, n in scored[:MAX_RELATED]]

    return ItemRelations(
        id=item_id,
        links=[_as_related(n) for n in links],
        backlinks=[_as_related(n) for n in backlinks],
        related=[_as_related(n) for n in related],
    )
