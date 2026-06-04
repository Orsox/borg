"""API router for the Dreaming system."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import get_current_user
from app.database import get_session
from app.dreaming import service
from app.dreaming.schemas import DreamingRunResponse, PaginatedDreamingRuns

router = APIRouter(prefix="/api/dreaming", tags=["dreaming"])


@router.post("/run")
async def trigger_dreaming(
    days: int = Query(default=14, ge=1, le=90),
    min_actions: int = Query(default=5, ge=1),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """Trigger a Dreaming consolidation cycle."""
    result = await service.run_dreaming_cycle(db, days=days, min_actions=min_actions)
    return result


@router.get("/runs", response_model=PaginatedDreamingRuns)
async def list_dreaming_runs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """Get Dreaming run history."""
    result = await service.get_dreaming_runs(db, page=page, size=size)
    return PaginatedDreamingRuns(
        items=[
            DreamingRunResponse(
                id=r.id,
                started_at=r.started_at,
                finished_at=r.finished_at,
                status=r.status,
                action_memories_analyzed=r.action_memories_analyzed,
                notes_created=r.notes_created,
                patterns_found=r.patterns_found,
                summary=r.summary,
                error=r.error,
            )
            for r in result["items"]
        ],
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
    )
