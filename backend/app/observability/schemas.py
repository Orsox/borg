"""Schemas for the observability (Langfuse) proxy API."""

from typing import Any, Optional

from pydantic import BaseModel


class ObservabilityStatus(BaseModel):
    configured: bool
    tracing_enabled: bool
    reachable: bool
    host: str
    ui_url: str
    error: Optional[str] = None


class TraceSummary(BaseModel):
    id: str
    timestamp: Optional[str] = None
    name: Optional[str] = None
    persona: Optional[str] = None  # Langfuse userId
    session_id: Optional[str] = None
    tags: list[str] = []
    latency_ms: Optional[float] = None
    level: Optional[str] = None
    input_preview: Optional[str] = None
    output_preview: Optional[str] = None
    ui_url: Optional[str] = None


class PaginatedTraces(BaseModel):
    items: list[TraceSummary]
    total: int
    page: int
    size: int
    pages: int


class ObservationSummary(BaseModel):
    id: str
    type: Optional[str] = None
    name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    level: Optional[str] = None
    status_message: Optional[str] = None
    model: Optional[str] = None
    usage: dict[str, Any] = {}
    input: Any = None
    output: Any = None
    parent_observation_id: Optional[str] = None


class TraceDetail(TraceSummary):
    input: Any = None
    output: Any = None
    metadata: Any = None
    observations: list[ObservationSummary] = []
