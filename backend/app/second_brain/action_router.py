"""API router for Action Memory module."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.second_brain import action_service as service
from app.second_brain.action_schemas import (
    ActionMemoryCreate,
    ActionMemoryListItem,
    ActionMemoryResponse,
    ActionMemoryStats,
    ActionMemoryUpdate,
    PaginatedActionMemories,
)
from app.auth.router import get_current_user
from app.database import get_session

router = APIRouter(prefix="/api/brain/actions", tags=["action_memory"])


@router.post("", response_model=ActionMemoryResponse, status_code=201)
async def create_action(
    body: ActionMemoryCreate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    action = await service.create_action_memory(
        db,
        title=body.title,
        description=body.description,
        action_type=body.action_type,
        tools_used=body.tools_used,
        status=body.status,
        duration_ms=body.duration_ms,
        output_path=body.output_path,
        metadata=body.metadata,
        tags=body.tags,
    )
    return ActionMemoryResponse(
        id=action.id,
        title=action.title,
        description=action.description,
        action_type=action.action_type,
        tools_used=json.loads(action.tools_used) if action.tools_used else [],
        status=action.status,
        is_archived=action.is_archived,
        duration_ms=action.duration_ms,
        output_path=action.output_path,
        metadata=json.loads(action.metadata_json) if action.metadata_json else {},
        tags=json.loads(action.tags) if action.tags else [],
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


@router.get("", response_model=PaginatedActionMemories)
async def list_actions(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    archived: bool = Query(default=False),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    result = await service.list_action_memories(
        db,
        page=page,
        size=size,
        search=search,
        action_type=action_type,
        status=status,
        archived=archived,
    )
    return PaginatedActionMemories(
        items=[
            ActionMemoryListItem(
                id=a.id,
                title=a.title,
                action_type=a.action_type,
                status=a.status,
                tools_used=json.loads(a.tools_used) if a.tools_used else [],
                tags=json.loads(a.tags) if a.tags else [],
                created_at=a.created_at,
                updated_at=a.updated_at,
            )
            for a in result["items"]
        ],
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
    )


@router.get("/stats", response_model=ActionMemoryStats)
async def get_stats(
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    stats = await service.get_action_memory_stats(db)
    return ActionMemoryStats(**stats)


@router.get("/{action_id}", response_model=ActionMemoryResponse)
async def get_action(
    action_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    action = await service.get_action_memory(db, action_id)
    if not action:
        raise HTTPException(status_code=404, detail=f"Action memory {action_id} not found")
    return ActionMemoryResponse(
        id=action.id,
        title=action.title,
        description=action.description,
        action_type=action.action_type,
        tools_used=json.loads(action.tools_used) if action.tools_used else [],
        status=action.status,
        is_archived=action.is_archived,
        duration_ms=action.duration_ms,
        output_path=action.output_path,
        metadata=json.loads(action.metadata_json) if action.metadata_json else {},
        tags=json.loads(action.tags) if action.tags else [],
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


@router.put("/{action_id}", response_model=ActionMemoryResponse)
async def update_action(
    action_id: int,
    body: ActionMemoryUpdate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    action = await service.update_action_memory(
        db,
        action_id=action_id,
        title=body.title,
        description=body.description,
        action_type=body.action_type,
        tools_used=body.tools_used,
        status=body.status,
        duration_ms=body.duration_ms,
        output_path=body.output_path,
        metadata=body.metadata,
        tags=body.tags,
    )
    if not action:
        raise HTTPException(status_code=404, detail=f"Action memory {action_id} not found")
    return ActionMemoryResponse(
        id=action.id,
        title=action.title,
        description=action.description,
        action_type=action.action_type,
        tools_used=json.loads(action.tools_used) if action.tools_used else [],
        status=action.status,
        is_archived=action.is_archived,
        duration_ms=action.duration_ms,
        output_path=action.output_path,
        metadata=json.loads(action.metadata_json) if action.metadata_json else {},
        tags=json.loads(action.tags) if action.tags else [],
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


@router.delete("/{action_id}", response_model=ActionMemoryResponse)
async def archive_action(
    action_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    action = await service.archive_action_memory(db, action_id)
    if not action:
        raise HTTPException(status_code=404, detail=f"Action memory {action_id} not found")
    return ActionMemoryResponse(
        id=action.id,
        title=action.title,
        description=action.description,
        action_type=action.action_type,
        tools_used=json.loads(action.tools_used) if action.tools_used else [],
        status=action.status,
        is_archived=action.is_archived,
        duration_ms=action.duration_ms,
        output_path=action.output_path,
        metadata=json.loads(action.metadata_json) if action.metadata_json else {},
        tags=json.loads(action.tags) if action.tags else [],
        created_at=action.created_at,
        updated_at=action.updated_at,
    )
