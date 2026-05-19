from enum import Enum
from pydantic import BaseModel
from typing import List

class NoteKind(str, Enum):
    """Defines the semantic type of a note based on its location or naming convention."""
    SOUL = "soul"        # SOUL.md at vault root
    USER = "user"        # USER.md at vault root
    MEMORY = "memory"    # MEMORY.md at vault root
    HABITS = "habits"    # HABITS.md at vault root
    HEARTBEAT = "heartbeat"  # HEARTBEAT.md at vault root
    DAILY = "daily"      # daily/*.md
    DRAFT = "draft"      # drafts/active/*, drafts/sent/*
    MEETING = "meeting"  # meetings/*.md
    PROJECT = "project"  # projects/*.md
    NOTE = "note"        # everything else (default)

class VaultGraphNode(BaseModel):
    """Represents a single note node in the graph."""
    id: str              # rel_path, used as edge endpoint identifier
    title: str           # Note title
    kind: NoteKind       # Semantic type of the note
    tags: List[str]      # Tags found in frontmatter
    backlink_count: int  # Number of other notes linking to this note
    rel_path: str        # Full path relative to vault root

class VaultGraphEdge(BaseModel):
    """Represents a directed link between two nodes."""
    source: str          # rel_path of source note (the source of the link)
    target: str          # rel_path of target note (the destination of the link)

class VaultGraph(BaseModel):
    """Container for the entire knowledge graph payload."""
    nodes: List[VaultGraphNode]
    edges: List[VaultGraphEdge]