"""API router for Improvement Insights."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import get_current_user
from app.database import get_session
from app.second_brain import insight_service as service
from app.second_brain.insight_models import ImprovementInsight
from app.second_brain.insight_schemas import (
    GenerateResult,
    InsightResponse,
    PaginatedInsights,
)

router = APIRouter(prefix="/api/brain/insights", tags=["insights"])


def _to_response(insight: ImprovementInsight) -> InsightResponse:
    return InsightResponse(
        id=insight.id,
        dedup_key=insight.dedup_key,
        category=insight.category,
        workflow=insight.workflow,
        summary=insight.summary,
        recommendation=insight.recommendation,
        evidence_action_ids=service._evidence_ids(insight),
        occurrences=insight.occurrences,
        status=insight.status,
        first_seen=insight.first_seen,
        last_seen=insight.last_seen,
        created_at=insight.created_at,
        updated_at=insight.updated_at,
    )


@router.get("", response_model=PaginatedInsights)
async def list_insights(
    status: str = Query(default="open"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    result = await service.list_insights(db, status=status, page=page, size=size)
    return PaginatedInsights(
        items=[_to_response(i) for i in result["items"]],
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
    )


@router.get("/top", response_model=list[InsightResponse])
async def top_insights(
    limit: int = Query(default=3, ge=1, le=10),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    insights = await service.get_top_insights(db, limit=limit)
    return [_to_response(i) for i in insights]


@router.post("/generate", response_model=GenerateResult)
async def generate(
    days: int = Query(default=14, ge=1, le=365),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    result = await service.generate_insights(db, days=days)
    return GenerateResult(
        created=result["created"],
        updated=result["updated"],
        total_open=result["total_open"],
    )


@router.post("/{insight_id}/acknowledge", response_model=InsightResponse)
async def acknowledge(
    insight_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    insight = await service.set_status(db, insight_id, "acknowledged")
    if insight is None:
        raise HTTPException(status_code=404, detail=f"Insight {insight_id} not found")
    return _to_response(insight)


@router.post("/{insight_id}/resolve", response_model=InsightResponse)
async def resolve(
    insight_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    insight = await service.set_status(db, insight_id, "resolved")
    if insight is None:
        raise HTTPException(status_code=404, detail=f"Insight {insight_id} not found")
    return _to_response(insight)
