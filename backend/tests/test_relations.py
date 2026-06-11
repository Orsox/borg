"""Tests for cross-source wiki-links and /api/brain/related."""

import pytest
from httpx import AsyncClient, ASGITransport


async def _login(client: AsyncClient) -> dict:
    login = await client.post(
        "/api/auth/token", data={"username": "borg", "password": "borgborg"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _make_vault(tmp_path):
    (tmp_path / "projects").mkdir()
    (tmp_path / "projects" / "borg.md").write_text(
        "---\ntitle: Borg Rollout\ntags: [infra]\n---\n"
        "Assimilation notes. See [[Cube Maintenance]] for the DB side.\n",
        encoding="utf-8",
    )
    (tmp_path / "intro.md").write_text(
        "Welcome. Start at [[Borg Rollout]].\n", encoding="utf-8"
    )


@pytest.mark.asyncio
async def test_cross_source_wiki_edges_in_combined_graph(tmp_path, monkeypatch):
    """[[targets]] unresolvable in their own source bridge into the other one."""
    from app.main import app

    _make_vault(tmp_path)
    monkeypatch.setattr("app.vault.router.VAULT", tmp_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login(client)

        # DB note links to a vault title; vault file links to this DB note title.
        note = (await client.post(
            "/api/brain/notes",
            json={"title": "Cube Maintenance", "content": "see [[Borg Rollout]]", "tags": []},
            headers=headers,
        )).json()

        resp = await client.get("/api/brain/graph/combined", headers=headers)
        assert resp.status_code == 200
        edges = {(e["source"], e["target"]) for e in resp.json()["edges"]}

        # note → vault (DB note's wiki-link fell back to vault title)
        assert (f"note:{note['id']}", "vault:projects/borg.md") in edges
        # vault → note (vault file's dangling link fell back to DB note title)
        assert ("vault:projects/borg.md", f"note:{note['id']}") not in edges  # deduped
        # vault-internal link still present
        assert ("vault:intro.md", "vault:projects/borg.md") in edges


@pytest.mark.asyncio
async def test_vault_to_note_edge_without_reverse(tmp_path, monkeypatch):
    """A vault link to a DB note title creates a vault→note edge."""
    from app.main import app

    (tmp_path / "log.md").write_text(
        "Today I worked on [[Warp Theory]].\n", encoding="utf-8"
    )
    monkeypatch.setattr("app.vault.router.VAULT", tmp_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login(client)
        note = (await client.post(
            "/api/brain/notes",
            json={"title": "Warp Theory", "content": "physics", "tags": []},
            headers=headers,
        )).json()

        resp = await client.get("/api/brain/graph/combined", headers=headers)
        edges = {(e["source"], e["target"]) for e in resp.json()["edges"]}
        assert ("vault:log.md", f"note:{note['id']}") in edges


@pytest.mark.asyncio
async def test_related_endpoint(tmp_path, monkeypatch):
    """/related returns cross-source links, backlinks, and tag neighbors."""
    from app.main import app

    _make_vault(tmp_path)
    monkeypatch.setattr("app.vault.router.VAULT", tmp_path)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login(client)

        note = (await client.post(
            "/api/brain/notes",
            json={
                "title": "Cube Maintenance",
                "content": "see [[Borg Rollout]]",
                "tags": ["infra"],
            },
            headers=headers,
        )).json()
        action = (await client.post(
            "/api/brain/actions",
            json={
                "title": "Provisioned cube",
                "action_type": "deploy",
                "status": "success",
                "tags": ["infra"],
            },
            headers=headers,
        )).json()

        resp = await client.get(
            f"/api/brain/related?id=note:{note['id']}", headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()

        link_ids = {r["id"] for r in data["links"]}
        backlink_ids = {r["id"] for r in data["backlinks"]}
        related_ids = {r["id"] for r in data["related"]}

        # Outgoing wiki-link into the vault. The vault file also links back to
        # this note's title, but the symmetric edge is deduped (note→vault is
        # added first), so it must not appear again as a backlink.
        assert "vault:projects/borg.md" in link_ids
        assert "vault:projects/borg.md" not in backlink_ids
        # Action shares the "infra" tag and is not wiki-linked → related.
        assert f"action:{action['id']}" in related_ids
        # The vault project note also has tag "infra" but is already linked → not repeated.
        assert "vault:projects/borg.md" not in related_ids

        # Relations from the vault side: the vault file links/backlinks the note.
        resp2 = await client.get(
            "/api/brain/related?id=vault:projects/borg.md", headers=headers
        )
        assert resp2.status_code == 200
        d2 = resp2.json()
        all_connected = {r["id"] for r in d2["links"]} | {r["id"] for r in d2["backlinks"]}
        assert f"note:{note['id']}" in all_connected
        assert "vault:intro.md" in all_connected


@pytest.mark.asyncio
async def test_related_unknown_item_404():
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login(client)
        resp = await client.get("/api/brain/related?id=note:99999", headers=headers)
        assert resp.status_code == 404
