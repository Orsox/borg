"""Tests for the Locutus audit trail (Stage 0 of the autonomy transition plan)."""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.locutus import service as locutus_service
from app.locutus.models import LocutusAuditEntry


async def _login_headers(client: AsyncClient) -> dict:
    login = await client.post("/api/auth/token", data={"username": "borg", "password": "borgborg"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _count_entries(action: str | None = None) -> int:
    async with AsyncSessionLocal() as db:
        query = select(func.count()).select_from(LocutusAuditEntry)
        if action:
            query = query.where(LocutusAuditEntry.action == action)
        return (await db.execute(query)).scalar() or 0


@pytest.mark.asyncio
async def test_record_action_creates_entry():
    """record_action() persists exactly one LocutusAuditEntry with the given fields."""
    async with AsyncSessionLocal() as db:
        entry = await locutus_service.record_action(
            db,
            action="test_action",
            actor="locutus",
            target="42",
            payload_summary="hello",
            result="ok",
        )
        assert entry.id is not None
        assert entry.created_at is not None

    assert await _count_entries("test_action") == 1

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(select(LocutusAuditEntry).where(LocutusAuditEntry.action == "test_action"))
        ).scalar_one()
        assert row.actor == "locutus"
        assert row.target == "42"
        assert row.payload_summary == "hello"
        assert row.result == "ok"


@pytest.mark.asyncio
async def test_character_memory_create_logs_audit_entry():
    """POST /api/locutus/memory produces one character_memory_create audit entry."""
    from app.main import app

    before = await _count_entries("character_memory_create")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login_headers(client)
        resp = await client.post(
            "/api/locutus/memory",
            json={"title": "Audit Memory", "content": "content", "category": "general"},
            headers=headers,
        )
        assert resp.status_code == 201
        mem_id = resp.json()["id"]

    after = await _count_entries("character_memory_create")
    assert after - before == 1

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(LocutusAuditEntry)
                .where(LocutusAuditEntry.action == "character_memory_create")
                .order_by(LocutusAuditEntry.created_at.desc())
            )
        ).scalars().first()
        assert row.target == str(mem_id)
        assert row.payload_summary == "Audit Memory"


@pytest.mark.asyncio
async def test_character_memory_archive_logs_audit_entry():
    """POST /api/locutus/memory/{id}/archive produces one character_memory_archive audit entry."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login_headers(client)
        create_resp = await client.post(
            "/api/locutus/memory",
            json={"title": "To Archive", "content": "content", "category": "general"},
            headers=headers,
        )
        mem_id = create_resp.json()["id"]

        before = await _count_entries("character_memory_archive")

        archive_resp = await client.post(f"/api/locutus/memory/{mem_id}/archive", headers=headers)
        assert archive_resp.status_code == 200

    after = await _count_entries("character_memory_archive")
    assert after - before == 1

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(LocutusAuditEntry)
                .where(LocutusAuditEntry.action == "character_memory_archive")
                .order_by(LocutusAuditEntry.created_at.desc())
            )
        ).scalars().first()
        assert row.target == str(mem_id)
        assert row.payload_summary == "To Archive"


@pytest.mark.asyncio
async def test_character_profile_update_logs_audit_entry():
    """POST /api/locutus/persona/character produces one character_profile_update audit entry."""
    from app.main import app

    before = await _count_entries("character_profile_update")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login_headers(client)
        new_content = "# Audit Test Persona\n\nSome content.\n"
        resp = await client.post(
            "/api/locutus/persona/character",
            json={"content": new_content},
            headers=headers,
        )
        assert resp.status_code == 201
        file_path = resp.json()["file_path"]

    after = await _count_entries("character_profile_update")
    assert after - before == 1

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(LocutusAuditEntry)
                .where(LocutusAuditEntry.action == "character_profile_update")
                .order_by(LocutusAuditEntry.created_at.desc())
            )
        ).scalars().first()
        assert row.target == file_path
        assert f"content_len={len(new_content)}" == row.payload_summary


@pytest.mark.asyncio
async def test_create_note_logs_audit_entry():
    """DiscordBotService.create_note() produces one note_create audit entry from the discord_bot actor."""
    from app.discord_bot.config import BotConfig
    from app.discord_bot.service import DiscordBotService

    config = BotConfig(enabled=True, token="test-token")
    service = DiscordBotService(config)

    before = await _count_entries("note_create")

    response = await service.create_note("Audit Note: created via test")
    assert not response.is_error

    after = await _count_entries("note_create")
    assert after - before == 1

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(LocutusAuditEntry)
                .where(LocutusAuditEntry.action == "note_create")
                .order_by(LocutusAuditEntry.created_at.desc())
            )
        ).scalars().first()
        assert row.actor == "discord_bot"
        assert row.result == "ok"
        assert row.payload_summary == "Audit Note"


@pytest.mark.asyncio
async def test_audit_list_endpoint_pagination_and_filters():
    """GET /api/locutus/audit returns newest-first, paginated, filterable results."""
    from app.main import app

    async with AsyncSessionLocal() as db:
        await locutus_service.record_action(db, action="alpha_action", actor="locutus")
        await locutus_service.record_action(db, action="beta_action", actor="discord_bot")
        await locutus_service.record_action(db, action="alpha_action", actor="discord_bot")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login_headers(client)

        resp = await client.get("/api/locutus/audit", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 3
        assert data["page"] == 1
        assert "pages" in data
        # newest-first ordering
        timestamps = [item["created_at"] for item in data["items"]]
        assert timestamps == sorted(timestamps, reverse=True)

        resp_actor = await client.get("/api/locutus/audit", params={"actor": "discord_bot"}, headers=headers)
        assert resp_actor.status_code == 200
        actor_items = resp_actor.json()["items"]
        assert len(actor_items) > 0
        assert all(item["actor"] == "discord_bot" for item in actor_items)

        resp_action = await client.get("/api/locutus/audit", params={"action": "alpha_action"}, headers=headers)
        assert resp_action.status_code == 200
        action_items = resp_action.json()["items"]
        assert len(action_items) > 0
        assert all(item["action"] == "alpha_action" for item in action_items)


@pytest.mark.asyncio
async def test_audit_endpoint_requires_auth():
    """GET /api/locutus/audit without credentials returns 401."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/locutus/audit")
        assert resp.status_code == 401
