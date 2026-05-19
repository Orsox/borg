"""FastAPI router for /api/archon-system endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.archon_system import service
from app.archon_system.schemas import (
    ArchonCodebasesResponse,
    ArchonRunsResponse,
    ArchonSystemHealthResponse,
    ArchonWorkflowsResponse,
    SyncResponse,
)
from app.auth.router import get_current_user
from app.database import get_session

router = APIRouter(prefix="/api/archon-system", tags=["archon_system"])


@router.post("/sync", response_model=SyncResponse)
async def sync(
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """Manually trigger a full sync from the Archon server."""
    return await service.sync_all(db)


@router.get("/health", response_model=ArchonSystemHealthResponse)
async def health(
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """Get current Archon system health status."""
    return await service.sync_and_get_health(db)


@router.get("/runs", response_model=ArchonRunsResponse)
async def runs(
    status: str = Query(default="all"),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """Get recent Archon workflow runs."""
    return await service.sync_and_get_runs(db, status=status, limit=limit)


@router.get("/codebases", response_model=ArchonCodebasesResponse)
async def codebases(
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """Get mirrored Archon codebases."""
    return await service.sync_and_get_codebases(db)


@router.get("/workflows", response_model=ArchonWorkflowsResponse)
async def workflows(
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """Get mirrored Archon workflows (metadata only, no nodes)."""
    return await service.sync_and_get_workflows(db)
