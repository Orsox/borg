"""Pydantic schemas for the Dreaming system."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DreamingRunResponse(BaseModel):
    id: int
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    action_memories_analyzed: int
    notes_created: int
    patterns_found: int
    summary: Optional[str]
    error: Optional[str]

    model_config = {"from_attributes": True}


class PaginatedDreamingRuns(BaseModel):
    items: list[DreamingRunResponse]
    total: int
    page: int
    size: int
    pages: int
