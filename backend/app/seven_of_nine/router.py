"""API router for the Seven of Nine module — persona, memory, audit, and chat."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import get_current_user
from app.database import get_session
from app.discord_bot.router import get_bot_service
from app.discord_bot.service import DiscordBotService
from app.seven_of_nine import service
from app.seven_of_nine.schemas import (
    DroneAuditEntryResponse,
    DroneMemoryCreate,
    DroneMemoryListItem,
    DroneMemoryResponse,
    DroneProfileCreate,
    DroneProfileResponse,
    PaginatedDroneAuditEntries,
    PaginatedDroneMemories,
)

router = APIRouter(prefix="/api/seven-of-nine", tags=["seven-of-nine"])


@router.get("/persona/profile", response_model=DroneProfileResponse)
async def get_profile(
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    profile = await service.get_or_create_profile(db)
    return DroneProfileResponse.model_validate(profile)


@router.post("/persona/profile", response_model=DroneProfileResponse, status_code=201)
async def update_profile(
    body: DroneProfileCreate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    profile = await service.update_profile(db, content=body.content)
    await service.record_action(
        db,
        action="drone_profile_update",
        target=str(profile.id),
        payload_summary=f"content_len={len(body.content)}",
    )
    return DroneProfileResponse.model_validate(profile)


@router.post("/memory", response_model=DroneMemoryResponse, status_code=201)
async def create_memory(
    body: DroneMemoryCreate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    entry = await service.create_memory(db, title=body.title, content=body.content, category=body.category)
    return DroneMemoryResponse.model_validate(entry)


@router.get("/memory", response_model=PaginatedDroneMemories)
async def list_memories(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
    archived: bool = Query(default=False),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    result = await service.list_memories(
        db, page=page, size=size, search=search, category=category, archived=archived
    )
    return PaginatedDroneMemories(
        items=[DroneMemoryListItem.model_validate(m) for m in result["items"]],
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
    )


@router.post("/memory/{entry_id}/archive")
async def archive_memory(
    entry_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    entry = await service.archive_memory(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return {"ok": True, "id": entry.id}


@router.get("/audit", response_model=PaginatedDroneAuditEntries)
async def list_audit_entries(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    actor: str | None = Query(default=None),
    action: str | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    result = await service.list_audit_entries(db, page=page, size=size, actor=actor, action=action)
    return PaginatedDroneAuditEntries(
        items=[DroneAuditEntryResponse.model_validate(e) for e in result["items"]],
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
    )


@router.post("/chat")
async def chat(
    message: str,
    user_id: int,
    _user=Depends(get_current_user),
    bot_service: DiscordBotService = Depends(get_bot_service),
):
    """Chat-Endpoint für Seven of Nine."""
    response = await bot_service.chat_as_seven(message, user_id)
    return {"content": response.content, "is_error": response.is_error}
