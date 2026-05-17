from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    content: str = Field(default="")
    tags: list[str] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=512)
    content: Optional[str] = Field(default=None)
    tags: Optional[list[str]] = Field(default=None)


class NoteResponse(BaseModel):
    id: int
    title: str
    content: str
    tags: list[str]
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoteListItem(BaseModel):
    id: int
    title: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedNotes(BaseModel):
    items: list[NoteListItem]
    total: int
    page: int
    size: int
    pages: int


class BacklinkItem(BaseModel):
    id: int
    title: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class GraphNode(BaseModel):
    id: int
    title: str
    tags: list[str]


class GraphEdge(BaseModel):
    source: int
    target: int


class KnowledgeGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
