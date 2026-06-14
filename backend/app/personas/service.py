"""Service layer for persona management.

CRUD operations on the Persona DB table plus startup seeding of default
personas (Locutus, Seven) from .env config when the table is empty.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.personas.models import Persona
from app.personas.schemas import (
    DiscordConfigSchema,
    LlmConfigSchema,
    PersonaCreate,
    PersonaUpdate,
)


# ── Helpers ────────────────────────────────────────────────────────


def _to_llm_config(persona: Persona) -> LlmConfigSchema:
    """Extract LLM config from a DB row into a Pydantic schema."""
    return LlmConfigSchema(
        base_url=persona.llm_base_url,
        model_id=persona.llm_model_id,
        context_window=persona.llm_context_window,
        max_tokens=persona.llm_max_tokens,
        temperature=persona.llm_temperature,
    )


def _to_discord_config(persona: Persona) -> DiscordConfigSchema:
    """Extract Discord config from a DB row into a Pydantic schema."""
    return DiscordConfigSchema(
        enabled=persona.discord_enabled,
        token=persona.discord_token,
        channel_id=persona.discord_channel_id,
        allowed_user_ids=persona.discord_allowed_user_ids,
        prefix=persona.discord_prefix,
        mention_prefix=persona.discord_mention_prefix,
    )


# ── CRUD operations ────────────────────────────────────────────────


async def list_personas(
    db: AsyncSession,
) -> dict:
    """List all personas (lightweight items without system_prompt)."""
    stmt = select(Persona).order_by(Persona.key)
    result = await db.execute(stmt)
    personas = result.scalars().all()

    items = []
    for p in personas:
        items.append({
            "id": p.id,
            "key": p.key,
            "display_name": p.display_name,
            "color": p.color,
            "llm_model_id": p.llm_model_id,
            "discord_enabled": p.discord_enabled,
            "is_active": p.is_active,
            "include_in_meetings": p.include_in_meetings,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        })

    return {"items": items, "total": len(items)}


async def get_persona(
    db: AsyncSession,
    persona_id: int,
) -> Optional[Persona]:
    """Fetch a single persona by ID, or None if not found."""
    stmt = select(Persona).where(Persona.id == persona_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_persona_by_key(
    db: AsyncSession,
    key: str,
) -> Optional[Persona]:
    """Fetch a single persona by its unique key."""
    stmt = select(Persona).where(Persona.key == key)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_persona(
    db: AsyncSession,
    body: PersonaCreate,
) -> Persona:
    """Create a new persona and persist to DB."""
    persona = Persona(
        key=body.key,
        display_name=body.display_name,
        color=body.color,
        system_prompt=body.system_prompt,
        llm_base_url=body.llm.base_url,
        llm_model_id=body.llm.model_id,
        llm_context_window=body.llm.context_window,
        llm_max_tokens=body.llm.max_tokens,
        llm_temperature=body.llm.temperature,
        discord_enabled=body.discord.enabled,
        discord_token=body.discord.token,
        discord_channel_id=body.discord.channel_id,
        discord_allowed_user_ids=body.discord.allowed_user_ids,
        discord_prefix=body.discord.prefix,
        discord_mention_prefix=body.discord.mention_prefix,
        is_active=body.is_active,
        include_in_meetings=body.include_in_meetings,
    )
    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    return persona


async def update_persona(
    db: AsyncSession,
    persona_id: int,
    body: PersonaUpdate,
) -> Optional[Persona]:
    """Partially update an existing persona. Returns None if not found."""
    persona = await get_persona(db, persona_id)
    if persona is None:
        return None

    # Update identity fields
    update_data = body.model_dump(exclude_unset=True)

    # Handle nested LLM config
    if body.llm is not None:
        persona.llm_base_url = body.llm.base_url
        persona.llm_model_id = body.llm.model_id
        persona.llm_context_window = body.llm.context_window
        persona.llm_max_tokens = body.llm.max_tokens
        persona.llm_temperature = body.llm.temperature
        update_data.pop("llm", None)

    # Handle nested Discord config
    if body.discord is not None:
        persona.discord_enabled = body.discord.enabled
        persona.discord_token = body.discord.token
        persona.discord_channel_id = body.discord.channel_id
        persona.discord_allowed_user_ids = body.discord.allowed_user_ids
        persona.discord_prefix = body.discord.prefix
        persona.discord_mention_prefix = body.discord.mention_prefix
        update_data.pop("discord", None)

    # Apply remaining top-level fields
    for field, value in update_data.items():
        setattr(persona, field, value)

    await db.commit()
    await db.refresh(persona)
    return persona


async def delete_persona(
    db: AsyncSession,
    persona_id: int,
) -> bool:
    """Delete a persona by ID. Returns True if deleted, False if not found."""
    persona = await get_persona(db, persona_id)
    if persona is None:
        return False
    await db.delete(persona)
    await db.commit()
    return True


# ── Seeding ────────────────────────────────────────────────────────


async def seed_default_personas(db: AsyncSession) -> int:
    """
    Seed default personas (Locutus, Seven of Nine) if the table is empty.

    Reads current .env settings and hardcoded system prompt constants to build
    initial DB rows. Only runs when no personas exist — idempotent.

    Returns the number of personas seeded (0 if table already had data).
    """
    # Check if any personas already exist
    count_stmt = select(Persona.id).limit(1)
    result = await db.execute(count_stmt)
    existing = result.scalars().first()
    if existing is not None:
        return 0

    # Import seed data sources (only needed at startup, so lazy import is fine)
    from app.config import settings
    from app.discord_bot.service import (
        LOCUTUS_SYSTEM_PROMPT,
        PERSONA_LOCUTUS,
        PERSONA_SEVEN,
        SEVEN_SYSTEM_PROMPT,
    )

    # ── Locutus ────────────────────────────────────────────────
    locutus = Persona(
        key=PERSONA_LOCUTUS,
        display_name="Locutus",
        color="#00e5ff",
        system_prompt=LOCUTUS_SYSTEM_PROMPT,
        llm_base_url=settings.discord_bot_locutus_llm_base_url,
        llm_model_id=settings.discord_bot_locutus_llm_model_id,
        llm_context_window=131072,
        llm_max_tokens=2048,
        llm_temperature=0.3,
        discord_enabled=settings.discord_bot_locutus_enabled,
        discord_token=settings.discord_bot_locutus_token if settings.discord_bot_locutus_enabled else None,
        discord_channel_id=settings.discord_bot_locutus_channel_id,
        discord_allowed_user_ids=(
            settings.discord_bot_locutus_allowed_user_ids or None
        ),
        discord_prefix=settings.discord_bot_locutus_prefix,
        discord_mention_prefix=settings.discord_bot_locutus_mention_prefix,
        is_active=True,
        include_in_meetings=True,
    )

    # ── Seven of Nine ──────────────────────────────────────────
    seven = Persona(
        key=PERSONA_SEVEN,
        display_name="Seven of Nine",
        color="#7cf67c",
        system_prompt=SEVEN_SYSTEM_PROMPT,
        llm_base_url=settings.discord_bot_seven_llm_base_url,
        llm_model_id=settings.discord_bot_seven_llm_model_id,
        llm_context_window=131072,
        llm_max_tokens=2048,
        llm_temperature=0.3,
        discord_enabled=settings.discord_bot_seven_enabled,
        discord_token=settings.discord_bot_seven_token if settings.discord_bot_seven_enabled else None,
        discord_channel_id=settings.discord_bot_seven_channel_id,
        discord_allowed_user_ids=(
            settings.discord_bot_seven_allowed_user_ids or None
        ),
        discord_prefix=settings.discord_bot_seven_prefix,
        discord_mention_prefix=settings.discord_bot_seven_mention_prefix,
        is_active=True,
        include_in_meetings=True,
    )

    db.add(locutus)
    db.add(seven)
    await db.commit()

    return 2


# ── Query helpers for consumers ────────────────────────────────────


async def list_active_personas(
    db: AsyncSession,
    include_meeting_only: bool = False,
) -> list[Persona]:
    """
    List active personas, optionally filtered to meeting participants.

    Args:
        db: Database session.
        include_meeting_only: If True, only return personas with
            include_in_meetings=True.

    Returns:
        Ordered list of active Persona rows (ordered by key for stability).
    """
    stmt = select(Persona).where(Persona.is_active == True)  # noqa: E712
    if include_meeting_only:
        stmt = stmt.where(Persona.include_in_meetings == True)  # noqa: E712
    stmt = stmt.order_by(Persona.key)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def build_llm_config(
    db: AsyncSession,
    persona_key: str,
) -> Optional["LlmConfig"]:  # type: ignore[name-defined]
    """
    Build a discord_bot LlmConfig from a DB persona row.

    Returns None if the persona key is not found or inactive.
    The returned LlmConfig is the same class used by DiscordBotService.
    """
    persona = await get_persona_by_key(db, persona_key)
    if persona is None or not persona.is_active:
        return None

    from app.discord_bot.config import LlmConfig

    return LlmConfig(
        persona=persona.key,
        base_url=persona.llm_base_url,
        model_id=persona.llm_model_id,
        context_window=persona.llm_context_window,
        max_tokens=persona.llm_max_tokens,
        temperature=persona.llm_temperature,
    )
