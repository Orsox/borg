"""Phase 2 smoke tests for Locutus persona and memory endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_get_character_profile():
    """GET /api/locutus/persona/character returns CharacterProfileResponse."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/auth/token", data={"username": "borg", "password": "borgborg"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        resp = await client.get("/api/locutus/persona/character", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"].startswith("# Locutus")
        assert "file_path" in data
        assert "last_synced_at" in data


@pytest.mark.asyncio
async def test_update_character_profile():
    """POST /api/locutus/persona/character updates both DB and filesystem."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/auth/token", data={"username": "borg", "password": "borgborg"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        new_content = "# Updated Locutus\n\nNew persona.\n"
        resp = await client.post(
            "/api/locutus/persona/character",
            json={"content": new_content},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == new_content


@pytest.mark.asyncio
async def test_get_character_file():
    """GET /api/locutus/persona/character/file reads directly from filesystem."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/auth/token", data={"username": "borg", "password": "borgborg"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # First update the profile to write to filesystem
        new_content = "# Filesystem Test\n\nHello world.\n"
        await client.post(
            "/api/locutus/persona/character",
            json={"content": new_content},
            headers=headers,
        )

        # Now read the file directly
        resp = await client.get("/api/locutus/persona/character/file", headers=headers)
        assert resp.status_code == 200
        assert "Filesystem Test" in resp.json()["content"]


@pytest.mark.asyncio
async def test_create_memory():
    """POST /api/locutus/memory creates a CharacterMemoryEntry."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/auth/token", data={"username": "borg", "password": "borgborg"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        resp = await client.post(
            "/api/locutus/memory",
            json={"title": "Test Memory", "content": "Some memory", "category": "general"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test Memory"
        assert data["category"] == "general"
        assert data["is_archived"] is False
        mem_id = data["id"]

        # Verify it appears in the list
        resp = await client.get("/api/locutus/memory", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1
        assert any(m["id"] == mem_id for m in resp.json()["items"])


@pytest.mark.asyncio
async def test_list_memories_with_filtering():
    """GET /api/locutus/memory returns paginated memories with filtering."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/auth/token", data={"username": "borg", "password": "borgborg"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # Create memories
        await client.post(
            "/api/locutus/memory",
            json={"title": "Alpha", "content": "a", "category": "general"},
            headers=headers,
        )
        await client.post(
            "/api/locutus/memory",
            json={"title": "Beta", "content": "b", "category": "preference"},
            headers=headers,
        )

        # Full list
        resp = await client.get("/api/locutus/memory", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

        # Search filter
        resp = await client.get("/api/locutus/memory?search=Alpha", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

        # Category filter
        resp = await client.get("/api/locutus/memory?category=preference", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

        # Archived filter (should be empty since none are archived)
        resp = await client.get("/api/locutus/memory?archived=true", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_archive_memory():
    """POST /api/locutus/memory/{id}/archive soft-deletes a memory."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/auth/token", data={"username": "borg", "password": "borgborg"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # Create a memory
        resp = await client.post(
            "/api/locutus/memory",
            json={"title": "To Archive", "content": "will be archived"},
            headers=headers,
        )
        mem_id = resp.json()["id"]

        # Archive it
        resp = await client.post(f"/api/locutus/memory/{mem_id}/archive", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Should be gone from default list
        resp = await client.get("/api/locutus/memory", headers=headers)
        assert resp.json()["total"] == 0

        # Should appear with archived=true
        resp = await client.get("/api/locutus/memory?archived=true", headers=headers)
        assert resp.json()["total"] >= 1

        # 404 for non-existent
        resp = await client.post("/api/locutus/memory/99999/archive", headers=headers)
        assert resp.status_code == 404
