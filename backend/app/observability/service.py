"""Mapping layer between the Langfuse public API and borg's compact schemas."""

import json
from typing import Any

from app.config import settings
from app.observability.schemas import ObservationSummary, PaginatedTraces, TraceDetail, TraceSummary

_PREVIEW_LIMIT = 200


def _preview(value: Any) -> str | None:
    """Render any trace input/output into a short single-line preview."""
    if value is None:
        return None
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            value = str(value)
    value = " ".join(value.split())
    if len(value) > _PREVIEW_LIMIT:
        return value[:_PREVIEW_LIMIT] + "…"
    return value or None


def trace_ui_url(trace_id: str) -> str | None:
    """Deep link into the Langfuse UI, when a public UI URL is configured."""
    if not settings.langfuse_ui_url:
        return None
    base = settings.langfuse_ui_url.rstrip("/")
    return f"{base}/project/{settings.langfuse_project_id}/traces/{trace_id}"


def _latency_ms(trace: dict[str, Any]) -> float | None:
    # Langfuse reports trace latency in seconds
    latency = trace.get("latency")
    if isinstance(latency, (int, float)):
        return round(latency * 1000, 1)
    return None


def map_trace_summary(trace: dict[str, Any]) -> TraceSummary:
    trace_id = str(trace.get("id", ""))
    return TraceSummary(
        id=trace_id,
        timestamp=trace.get("timestamp"),
        name=trace.get("name"),
        persona=trace.get("userId"),
        session_id=trace.get("sessionId"),
        tags=trace.get("tags") or [],
        latency_ms=_latency_ms(trace),
        level=trace.get("level"),
        input_preview=_preview(trace.get("input")),
        output_preview=_preview(trace.get("output")),
        ui_url=trace_ui_url(trace_id),
    )


def map_traces_page(data: dict[str, Any], page: int, size: int) -> PaginatedTraces:
    meta = data.get("meta") or {}
    return PaginatedTraces(
        items=[map_trace_summary(t) for t in data.get("data") or []],
        total=meta.get("totalItems", 0),
        page=meta.get("page", page),
        size=meta.get("limit", size),
        pages=meta.get("totalPages", 0),
    )


def _map_observation(obs: dict[str, Any]) -> ObservationSummary:
    usage = obs.get("usageDetails") or obs.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    return ObservationSummary(
        id=str(obs.get("id", "")),
        type=obs.get("type"),
        name=obs.get("name"),
        start_time=obs.get("startTime"),
        end_time=obs.get("endTime"),
        level=obs.get("level"),
        status_message=obs.get("statusMessage"),
        model=obs.get("model"),
        usage=usage,
        input=obs.get("input"),
        output=obs.get("output"),
        parent_observation_id=obs.get("parentObservationId"),
    )


def map_trace_detail(trace: dict[str, Any]) -> TraceDetail:
    summary = map_trace_summary(trace)
    observations = [_map_observation(o) for o in trace.get("observations") or []]
    # Chronological order makes the observation list read like a transcript
    observations.sort(key=lambda o: o.start_time or "")
    return TraceDetail(
        **summary.model_dump(),
        input=trace.get("input"),
        output=trace.get("output"),
        metadata=trace.get("metadata"),
        observations=observations,
    )
