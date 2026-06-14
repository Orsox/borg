"""Tests for persona management module."""

import pytest

from app.database import AsyncSessionLocal
from app.personas.models import Persona  # noqa: F401 — register model with Base
from app.personas.schemas import (
    DiscordConfigSchema,
    LlmConfigSchema,
    PersonaCreate,
    PersonaUpdate,
)
from app.personas.service import create_persona, delete_persona, get_persona, list_personas, update_persona


@pytest.mark.asyncio
async def test_create_and_list_persona():
    """Creating a persona makes it visible in the list."""
    async with AsyncSessionLocal() as db:
        body = PersonaCreate(
            key="test-persona",
            display_name="Test Character",
            color="#ff0000",
            llm=LlmConfigSchema(model_id="test-model"),
        )
        created = await create_persona(db, body)

    assert created.id is not None
    assert created.key == "test-persona"
    assert created.llm_model_id == "test-model"

    async with AsyncSessionLocal() as db:
        result = await list_personas(db)

    assert result["total"] >= 1
    keys = [item["key"] for item in result["items"]]
    assert "test-persona" in keys


@pytest.mark.asyncio
async def test_get_persona_by_id():
    """Getting a persona by ID returns full details."""
    async with AsyncSessionLocal() as db:
        body = PersonaCreate(
            key="get-test",
            display_name="Get Test",
            system_prompt="You are a test character.",
        )
        created = await create_persona(db, body)

    async with AsyncSessionLocal() as db:
        fetched = await get_persona(db, created.id)

    assert fetched is not None
    assert fetched.system_prompt == "You are a test character."
    assert fetched.display_name == "Get Test"


@pytest.mark.asyncio
async def test_get_nonexistent_persona_returns_none():
    """Getting a persona that doesn't exist returns None."""
    async with AsyncSessionLocal() as db:
        result = await get_persona(db, 9999)
    assert result is None


@pytest.mark.asyncio
async def test_update_persona_partial():
    """Partial update only changes provided fields."""
    async with AsyncSessionLocal() as db:
        body = PersonaCreate(
            key="update-test",
            display_name="Original Name",
            llm=LlmConfigSchema(model_id="old-model"),
        )
        created = await create_persona(db, body)

    async with AsyncSessionLocal() as db:
        updated = await update_persona(
            db, created.id, PersonaUpdate(display_name="New Name"),
        )

    assert updated is not None
    assert updated.display_name == "New Name"
    assert updated.llm_model_id == "old-model"  # unchanged


@pytest.mark.asyncio
async def test_update_persona_llm_config():
    """Updating nested LLM config replaces all LLM fields."""
    async with AsyncSessionLocal() as db:
        body = PersonaCreate(
            key="llm-update-test",
            display_name="LLM Test",
            llm=LlmConfigSchema(model_id="old-model", temperature=0.5),
        )
        created = await create_persona(db, body)

    async with AsyncSessionLocal() as db:
        updated = await update_persona(
            db, created.id,
            PersonaUpdate(llm=LlmConfigSchema(model_id="new-model", max_tokens=4096)),
        )

    assert updated is not None
    assert updated.llm_model_id == "new-model"
    assert updated.llm_max_tokens == 4096


@pytest.mark.asyncio
async def test_update_nonexistent_persona_returns_none():
    """Updating a persona that doesn't exist returns None."""
    async with AsyncSessionLocal() as db:
        result = await update_persona(
            db, 9999, PersonaUpdate(display_name="Ghost"),
        )
    assert result is None


@pytest.mark.asyncio
async def test_delete_persona():
    """Deleting a persona removes it from the list."""
    async with AsyncSessionLocal() as db:
        body = PersonaCreate(key="delete-test", display_name="Delete Me")
        created = await create_persona(db, body)

    async with AsyncSessionLocal() as db:
        deleted = await delete_persona(db, created.id)
    assert deleted is True

    async with AsyncSessionLocal() as db:
        fetched = await get_persona(db, created.id)
    assert fetched is None


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_false():
    """Deleting a persona that doesn't exist returns False."""
    async with AsyncSessionLocal() as db:
        result = await delete_persona(db, 9999)
    assert result is False


@pytest.mark.asyncio
async def test_duplicate_key_raises():
    """Creating two personas with the same key raises an integrity error."""
    async with AsyncSessionLocal() as db:
        body1 = PersonaCreate(key="dup-key", display_name="First")
        await create_persona(db, body1)

        body2 = PersonaCreate(key="dup-key", display_name="Second")
        with pytest.raises(Exception):
            await create_persona(db, body2)


@pytest.mark.asyncio
async def test_discord_config_roundtrip():
    """Discord config fields are stored and retrieved correctly."""
    async with AsyncSessionLocal() as db:
        body = PersonaCreate(
            key="discord-test",
            display_name="Discord Test",
            discord=DiscordConfigSchema(
                enabled=True,
                token="fake-token-123",
                channel_id=123456789,
                allowed_user_ids="111,222",
                prefix="/",
                mention_prefix="@TestBot",
            ),
        )
        created = await create_persona(db, body)

    assert created.discord_enabled is True
    assert created.discord_token == "fake-token-123"
    assert created.discord_channel_id == 123456789
    assert created.discord_allowed_user_ids == "111,222"
    assert created.discord_prefix == "/"
    assert created.discord_mention_prefix == "@TestBot"
