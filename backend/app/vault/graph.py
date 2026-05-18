"""Vault graph builder — classifies notes, resolves wiki-links, computes backlinks."""

import logging
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .scanner import ParsedNote
from .schemas import VaultGraph, VaultGraphNode, VaultGraphEdge, NoteKind

logger = logging.getLogger(__name__)

# ── Classification ─────────────────────────────────────────────────────────────

SPECIAL_FILES = {
    "soul.md": NoteKind.SOUL,
    "user.md": NoteKind.USER,
    "memory.md": NoteKind.MEMORY,
    "habits.md": NoteKind.HABITS,
    "heartbeat.md": NoteKind.HEARTBEAT,
}

FOLDER_KINDS: Dict[str, NoteKind] = {
    "daily": NoteKind.DAILY,
    "drafts": NoteKind.DRAFT,
    "meetings": NoteKind.MEETING,
    "projects": NoteKind.PROJECT,
}


def classify(parsed: ParsedNote) -> NoteKind:
    """Classify a note's kind based on its relative path and filename.

    Priority:
      1. Special-file rules (root-level SOUL.md, USER.md, …)
      2. Path-prefix rules (daily/, drafts/, meetings/, projects/)
      3. Default → NOTE
    """
    rel = Path(parsed.rel_path)
    stem_lower = rel.name.lower()

    # Rule 1: special files at vault root (no parent directories)
    if rel.parent == Path("."):
        if stem_lower in SPECIAL_FILES:
            return SPECIAL_FILES[stem_lower]

    # Rule 2: folder prefix
    first_part = rel.parts[0].lower() if rel.parts else ""
    if first_part in FOLDER_KINDS:
        return FOLDER_KINDS[first_part]

    return NoteKind.NOTE


# ── Link Resolution ────────────────────────────────────────────────────────────

def resolve_link(
    target: str,
    by_title: Dict[str, str],
    by_relpath: Dict[str, str],
) -> str | None:
    """Resolve a wiki-link target string to a note's relative path.

    Resolution order:
      1. Exact rel_path match (with or without .md suffix)
      2. Exact title match (case-insensitive)
      3. None (dangling link — dropped silently)
    """
    # 1. Direct rel_path match
    if target in by_relpath:
        return by_relpath[target]

    # 2. Title match (case-insensitive)
    target_lower = target.strip().lower()
    if target_lower in by_title:
        return by_title[target_lower]

    logger.debug("Dangling wiki-link dropped: %s", target)
    return None


# ── Graph Builder ──────────────────────────────────────────────────────────────

def build_vault_graph(notes: List[ParsedNote]) -> VaultGraph:
    """Build the complete VaultGraph from scanned notes.

    Steps:
      1. Classify each note and build lookup indices
      2. Resolve all wiki-link targets to edges
      3. Compute backlink counts
      4. Return VaultGraph
    """
    if not notes:
        return VaultGraph(nodes=[], edges=[])

    # Build lookup indices
    by_title: Dict[str, str] = {}       # title (lower) → rel_path
    by_relpath: Dict[str, str] = {}     # rel_path → rel_path
    by_relpath_stem: Dict[str, str] = {}  # rel_path without .md → rel_path

    for note in notes:
        by_title[note.title.lower()] = note.rel_path
        by_relpath[note.rel_path] = note.rel_path
        # Also index without .md suffix so [[folder/B]] resolves to folder/B.md
        stem = note.rel_path.removesuffix(".md")
        by_relpath_stem[stem] = note.rel_path

    # Merge stem index into relpath index (relpath takes priority)
    for key, val in by_relpath_stem.items():
        by_relpath.setdefault(key, val)

    # Classify and collect edges
    edge_set: Set[Tuple[str, str]] = set()
    node_map: Dict[str, ParsedNote] = {}

    for note in notes:
        node_map[note.rel_path] = note

        for raw_target in note.wiki_targets:
            resolved = resolve_link(raw_target, by_title, by_relpath)
            if resolved and resolved != note.rel_path:  # no self-links
                edge_set.add((note.rel_path, resolved))

    # Compute backlink counts
    backlink_counts: Dict[str, int] = {note.rel_path: 0 for note in notes}
    for _, target_path in edge_set:
        if target_path in backlink_counts:
            backlink_counts[target_path] += 1

    # Build nodes
    nodes: List[VaultGraphNode] = []
    for note in notes:
        kind = classify(note)
        nodes.append(VaultGraphNode(
            id=note.rel_path,
            title=note.title,
            kind=kind,
            tags=note.tags,
            backlink_count=backlink_counts.get(note.rel_path, 0),
            rel_path=note.rel_path,
        ))

    # Build edges
    edges: List[VaultGraphEdge] = [
        VaultGraphEdge(source=s, target=t)
        for s, t in edge_set
        if s in node_map and t in node_map
    ]

    return VaultGraph(nodes=nodes, edges=edges)
