"""Tests for the peer-facing manifest endpoint and local manifest builder."""

from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

from app.archon_hub.models import ArchonAsset
from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_manifest_requires_token_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "peer_sync_token", "")
    async with _client() as client:
        resp = await client.get("/api/peer/manifest")
        assert resp.status_code == 403


async def test_manifest_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(settings, "peer_sync_token", "secret")
    async with _client() as client:
        resp = await client.get(
            "/api/peer/manifest", headers={"Authorization": "Bearer nope"}
        )
        assert resp.status_code == 403


async def test_manifest_returns_relative_identities(monkeypatch, tmp_path):
    archon_root = tmp_path / "archon"
    (archon_root / "workflows").mkdir(parents=True)
    monkeypatch.setattr(settings, "archon_path", str(archon_root))
    monkeypatch.setattr(settings, "peer_sync_token", "secret")

    abs_path = str((archon_root / "workflows" / "demo.yaml").resolve())
    async with AsyncSessionLocal() as db:
        db.add(
            ArchonAsset(
                name="demo",
                type="workflow",
                description=None,
                tags="[]",
                file_path=abs_path,
                raw_content="name: demo\n",
                last_scanned=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    async with _client() as client:
        resp = await client.get(
            "/api/peer/manifest", headers={"Authorization": "Bearer secret"}
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        demo = next(i for i in items if i["kind"] == "workflow")
        # Cross-machine-stable identity is the path relative to ARCHON_PATH.
        assert demo["identity"] == "workflows/demo.yaml"
        assert demo["content_hash"]
