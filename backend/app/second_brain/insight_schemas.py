"""Pydantic schemas for Improvement Insights."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class InsightResponse(BaseModel):
    id: int
    dedup_key: str
    category: str
    workflow: Optional[str]
    summary: str
    recommendation: str
    evidence_action_ids: list[int]
    occurrences: int
    status: str
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class PaginatedInsights(BaseModel):
    items: list[InsightResponse]
    total: int
    page: int
    size: int
    pages: int


class GenerateResult(BaseModel):
    created: int
    updated: int
    total_open: int
