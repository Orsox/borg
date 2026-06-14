"""API router for persona management.

Provides CRUD endpoints for creating, reading, updating, and deleting
persona definitions stored in the database. All routes require authentication;
delete requires admin privileges.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.router import get_current_admin, get_current_user
from app.database import get_session
from app.personas import service
from app.personas.schemas import (
    DiscordConfigSchema,
    LlmConfigSchema,
    PersonaCreate,
    PersonaListItem,
    PersonaListResponse,
    PersonaResponse,
    PersonaUpdate,
)

router = APIRouter(prefix="/api/personas", tags=["personas"])


@router.get("", response_model=PersonaListResponse)
async def list_personas_api(
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """List all personas (lightweight, excludes system prompts)."""
    data = await service.list_personas(db)
    items = [PersonaListItem(**item) for item in data["items"]]
    return PersonaListResponse(items=items, total=data["total"])


@router.get("/{persona_id}", response_model=PersonaResponse)
async def get_persona_api(
    persona_id: int,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """Get full details of a single persona (includes system prompt)."""
    persona = await service.get_persona(db, persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail=f"Persona {persona_id} not found")

    return PersonaResponse(
        id=persona.id,
        key=persona.key,
        display_name=persona.display_name,
        color=persona.color,
        system_prompt=persona.system_prompt,
        llm=_to_llm_schema(persona),
        discord=_to_discord_schema(persona),
        is_active=persona.is_active,
        include_in_meetings=persona.include_in_meetings,
        created_at=persona.created_at,
        updated_at=persona.updated_at,
    )


@router.post("", response_model=PersonaResponse, status_code=201)
async def create_persona_api(
    body: PersonaCreate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """Create a new persona."""
    try:
        persona = await service.create_persona(db, body)
    except Exception as e:
        if "unique" in str(e).lower() or "UNIQUE" in str(e):
            raise HTTPException(
                status_code=409, detail=f"Persona with key '{body.key}' already exists",
            )
        raise

    return _persona_to_response(persona)


@router.put("/{persona_id}", response_model=PersonaResponse)
async def update_persona_api(
    persona_id: int,
    body: PersonaUpdate,
    db: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """Partially update an existing persona."""
    persona = await service.update_persona(db, persona_id, body)
    if persona is None:
        raise HTTPException(status_code=404, detail=f"Persona {persona_id} not found")
    return _persona_to_response(persona)


@router.delete("/{persona_id}", status_code=204)
async def delete_persona_api(
    persona_id: int,
    db: AsyncSession = Depends(get_session),
    _admin=Depends(get_current_admin),
):
    """Delete a persona. Requires admin privileges."""
    deleted = await service.delete_persona(db, persona_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Persona {persona_id} not found")


# ── Response builders ──────────────────────────────────────────────


def _to_llm_schema(persona) -> LlmConfigSchema:
    return LlmConfigSchema(
        base_url=persona.llm_base_url,
        model_id=persona.llm_model_id,
        context_window=persona.llm_context_window,
        max_tokens=persona.llm_max_tokens,
        temperature=float(persona.llm_temperature),
    )


def _to_discord_schema(persona) -> DiscordConfigSchema:
    return DiscordConfigSchema(
        enabled=persona.discord_enabled,
        token="***" if persona.discord_token else None,  # Mask tokens in API responses
        channel_id=persona.discord_channel_id,
        allowed_user_ids=persona.discord_allowed_user_ids,
        prefix=persona.discord_prefix,
        mention_prefix=persona.discord_mention_prefix,
    )


def _persona_to_response(persona) -> PersonaResponse:
    return PersonaResponse(
        id=persona.id,
        key=persona.key,
        display_name=persona.display_name,
        color=persona.color,
        system_prompt=persona.system_prompt,
        llm=_to_llm_schema(persona),
        discord=_to_discord_schema(persona),
        is_active=persona.is_active,
        include_in_meetings=persona.include_in_meetings,
        created_at=persona.created_at,
        updated_at=persona.updated_at,
    )
