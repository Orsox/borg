"""Pydantic schemas for the Seven of Nine module."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- Drone Profile ---

class DroneProfileCreate(BaseModel):
    content: str = Field(..., min_length=1)


class DroneProfileResponse(BaseModel):
    id: int
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Drone Memory ---

class DroneMemoryCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    content: str = Field(default="")
    category: str = Field(default="general", max_length=64)


class DroneMemoryResponse(BaseModel):
    id: int
    title: str
    content: str
    category: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DroneMemoryListItem(BaseModel):
    id: int
    title: str
    category: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedDroneMemories(BaseModel):
    items: list[DroneMemoryListItem]
    total: int
    page: int
    size: int
    pages: int


# --- Audit Trail ---

class DroneAuditEntryResponse(BaseModel):
    id: int
    run_id: Optional[str]
    actor: str
    action: str
    target: Optional[str]
    payload_summary: Optional[str]
    result: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedDroneAuditEntries(BaseModel):
    items: list[DroneAuditEntryResponse]
    total: int
    page: int
    size: int
    pages: int
