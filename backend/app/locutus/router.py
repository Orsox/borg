"""API router for Locutus module — persona, memory, evolution, and skill management."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import get_current_user
from app.database import get_session
from app.locutus import service
from app.locutus.schemas import (
    AuditEntryResponse,
    CharacterMemoryCreate,
    CharacterMemoryListItem,
    CharacterMemoryResponse,
    CharacterProfileCreate,
    CharacterProfileResponse,
    PaginatedAuditEntries,
    PaginatedMemories,
    PaginatedReasoningLogs,
    ReasoningLogDecision,
    ReasoningLogListItem,
    ReasoningLogResponse,
)

router = APIRouter(prefix="/api/locutus", tags=["locutus"])


@router.get("/persona/character", response_model=CharacterProfileResponse)
async def get_character_profile(
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    profile = await service.get_or_create_character_profile(db)
    return CharacterProfileResponse(
        id=profile.id,
        content=profile.content,
        file_path=profile.file_path,
        last_synced_at=profile.last_synced_at,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.post("/persona/character", response_model=CharacterProfileResponse, status_code=201)
async def update_character_profile(
    body: CharacterProfileCreate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    profile = await service.update_character_profile(db, content=body.content, file_path=body.file_path)

    # Also write to filesystem
    await service.write_character_file(body.content, body.file_path)

    await service.record_action(
        db,
        action="character_profile_update",
        target=profile.file_path,
        payload_summary=f"content_len={len(body.content)}",
    )

    return CharacterProfileResponse(
        id=profile.id,
        content=profile.content,
        file_path=profile.file_path,
        last_synced_at=profile.last_synced_at,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.get("/persona/character/file")
async def get_character_file(
    _user=Depends(get_current_user),
):
    """Read the Character.md file directly from filesystem."""
    content = await service.read_character_file()
    return {"content": content}


@router.post("/memory", response_model=CharacterMemoryResponse, status_code=201)
async def create_memory(
    body: CharacterMemoryCreate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    entry = await service.create_character_memory(
        db, title=body.title, content=body.content, category=body.category
    )
    return CharacterMemoryResponse(
        id=entry.id,
        title=entry.title,
        content=entry.content,
        category=entry.category,
        is_archived=entry.is_archived,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.get("/memory", response_model=PaginatedMemories)
async def list_memories(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
    archived: bool = Query(default=False),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    result = await service.list_character_memories(
        db, page=page, size=size, search=search, category=category, archived=archived
    )
    return PaginatedMemories(
        items=[
            CharacterMemoryListItem(
                id=m.id,
                title=m.title,
                category=m.category,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in result["items"]
        ],
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
    entry = await service.archive_character_memory(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return {"ok": True, "id": entry.id}


@router.get("/reasoning", response_model=PaginatedReasoningLogs)
async def list_reasoning_logs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    result = await service.list_reasoning_logs(db, page=page, size=size, status=status)
    return PaginatedReasoningLogs(
        items=[ReasoningLogListItem.model_validate(log) for log in result["items"]],
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
    )


@router.post("/reasoning/{log_id}/decision", response_model=ReasoningLogResponse)
async def decide_reasoning_log(
    log_id: int,
    body: ReasoningLogDecision,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """Approve or reject a draft ReasoningLog — the explicit human decision point.

    The only code path allowed to move a ReasoningLog out of `draft`. Approval
    is checked against the weekly EvolutionBudget here (not at proposal time).
    """
    try:
        log = await service.decide_reasoning_log(db, log_id, decision=body.decision, note=body.note)
    except service.ReasoningLogNotFound:
        raise HTTPException(status_code=404, detail="Reasoning log not found")
    except service.ReasoningLogNotDraft as e:
        raise HTTPException(status_code=409, detail=str(e))
    except service.EvolutionBudgetExhausted as e:
        raise HTTPException(status_code=429, detail=str(e))

    return ReasoningLogResponse.model_validate(log)


@router.get("/audit", response_model=PaginatedAuditEntries)
async def list_audit_entries(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    actor: str | None = Query(default=None),
    action: str | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    result = await service.list_audit_entries(db, page=page, size=size, actor=actor, action=action)
    return PaginatedAuditEntries(
        items=[AuditEntryResponse.model_validate(e) for e in result["items"]],
        total=result["total"],
        page=result["page"],
        size=result["size"],
        pages=result["pages"],
    )
