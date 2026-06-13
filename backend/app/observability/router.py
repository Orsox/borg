"""API router for the observability (Langfuse) integration.

Server-side proxy to the Langfuse public API: the borg frontend renders traces
in its own theme and never sees the Langfuse secret key. Mirrors the
archon_system pattern — one Unavailable exception, graceful status reporting.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.router import get_current_user
from app.config import settings
from app.observability import service
from app.observability.client import LangfuseApiClient, LangfuseUnavailable, is_configured
from app.observability.schemas import ObservabilityStatus, PaginatedTraces, TraceDetail

router = APIRouter(prefix="/api/observability", tags=["observability"])


@router.get("/status", response_model=ObservabilityStatus)
async def get_status(_user=Depends(get_current_user)):
    """Configuration + reachability of the Langfuse stack."""
    configured = is_configured()
    reachable = False
    error: str | None = None
    if configured:
        try:
            async with LangfuseApiClient() as client:
                await client.get_health()
            reachable = True
        except LangfuseUnavailable as e:
            error = e.reason or str(e)
    return ObservabilityStatus(
        configured=configured,
        tracing_enabled=settings.langfuse_enabled,
        reachable=reachable,
        host=settings.langfuse_host,
        ui_url=settings.langfuse_ui_url,
        error=error,
    )


@router.get("/traces", response_model=PaginatedTraces)
async def list_traces(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=100),
    persona: str | None = Query(default=None, max_length=64),
    tag: str | None = Query(default=None, max_length=64),
    session_id: str | None = Query(default=None, max_length=128),
    _user=Depends(get_current_user),
):
    """Recent traces, newest first — filterable by persona, surface tag, session."""
    if not is_configured():
        raise HTTPException(status_code=503, detail="Langfuse is not configured (missing API keys)")
    try:
        async with LangfuseApiClient() as client:
            data = await client.list_traces(
                page=page,
                limit=size,
                user_id=persona,
                session_id=session_id,
                tags=[tag] if tag else None,
            )
    except LangfuseUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    return service.map_traces_page(data, page, size)


@router.get("/traces/{trace_id}", response_model=TraceDetail)
async def get_trace(trace_id: str, _user=Depends(get_current_user)):
    """One trace with its full observation tree (spans + generations)."""
    if not is_configured():
        raise HTTPException(status_code=503, detail="Langfuse is not configured (missing API keys)")
    try:
        async with LangfuseApiClient() as client:
            data = await client.get_trace(trace_id)
    except LangfuseUnavailable as e:
        if "HTTP 404" in (e.reason or ""):
            raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
        raise HTTPException(status_code=503, detail=str(e))
    return service.map_trace_detail(data)
