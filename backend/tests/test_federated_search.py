"""Tests for the federated brain search (/api/brain/search)."""

import pytest
from httpx import AsyncClient, ASGITransport


async def _login(client: AsyncClient) -> dict:
    login = await client.post(
        "/api/auth/token", data={"username": "borg", "password": "borgborg"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_search_requires_auth():
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/brain/search?q=anything")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_search_notes_and_actions():
    """Federated search returns namespaced hits from notes and actions, title matches first."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login(client)

        await client.post(
            "/api/brain/notes",
            json={"title": "Quantum networking", "content": "entanglement basics", "tags": []},
            headers=headers,
        )
        await client.post(
            "/api/brain/notes",
            json={"title": "Daily log", "content": "studied quantum stuff today", "tags": []},
            headers=headers,
        )
        await client.post(
            "/api/brain/actions",
            json={
                "title": "Ran quantum sim",
                "description": "simulated circuits",
                "action_type": "test",
                "status": "success",
                "tags": ["physics"],
            },
            headers=headers,
        )

        resp = await client.get(
            "/api/brain/search?q=quantum&sources=note,action", headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "quantum"
        assert data["sources"] == ["action", "note"]

        results = data["results"]
        ids = {r["id"] for r in results}
        assert any(i.startswith("note:") for i in ids)
        assert any(i.startswith("action:") for i in ids)

        # Title matches (score 3) rank above the content-only match (score 1).
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)
        content_hit = next(r for r in results if r["title"] == "Daily log")
        assert content_hit["score"] == 1
        assert "quantum" in content_hit["snippet"].lower()

        # Every result carries the fields the detail view needs.
        for r in results:
            assert r["source"] in {"note", "action"}
            assert r["ref"]
            assert r["kind"]


@pytest.mark.asyncio
async def test_search_vault_source(tmp_path, monkeypatch):
    """Vault hits come from markdown scan with kind classification and snippets."""
    from app.main import app

    (tmp_path / "projects").mkdir()
    (tmp_path / "projects" / "borg.md").write_text(
        "---\ntitle: Borg Rollout\ntags: [infra]\n---\nCube assimilation notes.\n",
        encoding="utf-8",
    )
    (tmp_path / "random.md").write_text(
        "Nothing about the query here.\n", encoding="utf-8"
    )
    monkeypatch.setattr("app.vault.router.VAULT", tmp_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login(client)
        resp = await client.get(
            "/api/brain/search?q=assimilation&sources=vault", headers=headers
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        hit = results[0]
        assert hit["id"] == "vault:projects/borg.md"
        assert hit["source"] == "vault"
        assert hit["kind"] == "project"
        assert hit["ref"] == "projects/borg.md"
        assert "assimilation" in hit["snippet"].lower()
        assert hit["score"] == 1  # content match


@pytest.mark.asyncio
async def test_browse_mode_lists_all_newest_first(tmp_path, monkeypatch):
    """Empty q returns all items from selected sources ordered by updated_at desc."""
    from app.main import app

    (tmp_path / "old.md").write_text("ancient lore\n", encoding="utf-8")
    monkeypatch.setattr("app.vault.router.VAULT", tmp_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login(client)

        await client.post(
            "/api/brain/notes",
            json={"title": "First note", "content": "alpha", "tags": []},
            headers=headers,
        )
        await client.post(
            "/api/brain/actions",
            json={"title": "Some action", "action_type": "test", "status": "success"},
            headers=headers,
        )

        resp = await client.get("/api/brain/search", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == ""

        results = data["results"]
        sources = {r["source"] for r in results}
        assert {"note", "action", "vault"} <= sources
        assert all(r["score"] == 0 for r in results)
        assert all(r["updated_at"] is not None for r in results)

        # Newest first across sources (DB rows just created beat the vault file).
        timestamps = [r["updated_at"] for r in results]
        assert results[0]["source"] in {"note", "action"}
        assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.asyncio
async def test_search_rejects_unknown_sources():
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login(client)
        resp = await client.get("/api/brain/search?q=x&sources=bogus", headers=headers)
        assert resp.status_code == 400
