"""Pydantic schemas for Action Memory."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ActionMemoryCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    description: str = Field(default="")
    action_type: str = Field(default="general", max_length=64)
    tools_used: list[str] = Field(default_factory=list)
    status: str = Field(default="success", max_length=32)
    duration_ms: Optional[int] = Field(default=None)
    output_path: Optional[str] = Field(default=None, max_length=1024)
    metadata: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ActionMemoryUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=512)
    description: Optional[str] = Field(default=None)
    action_type: Optional[str] = Field(default=None, max_length=64)
    tools_used: Optional[list[str]] = Field(default=None)
    status: Optional[str] = Field(default=None, max_length=32)
    duration_ms: Optional[int] = Field(default=None)
    output_path: Optional[str] = Field(default=None, max_length=1024)
    metadata: Optional[dict] = Field(default=None)
    tags: Optional[list[str]] = Field(default=None)


class ActionMemoryResponse(BaseModel):
    id: int
    title: str
    description: str
    action_type: str
    tools_used: list[str]
    status: str
    is_archived: bool
    duration_ms: Optional[int]
    output_path: Optional[str]
    metadata: dict
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ActionMemoryListItem(BaseModel):
    id: int
    title: str
    action_type: str
    status: str
    tools_used: list[str]
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedActionMemories(BaseModel):
    items: list[ActionMemoryListItem]
    total: int
    page: int
    size: int
    pages: int


class ActionMemoryStats(BaseModel):
    total: int
    success_count: int
    failed_count: int
    in_progress_count: int
    action_types: list[dict]
