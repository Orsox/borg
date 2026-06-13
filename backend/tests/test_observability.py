"""Tests for the observability (Langfuse proxy) API."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.observability import router as obs_router
from app.observability import service as obs_service


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _login(client: AsyncClient) -> dict[str, str]:
    login = await client.post(
        "/api/auth/token", data={"username": "borg", "password": "borgborg"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_status_reports_unconfigured_by_default():
    async with _client() as client:
        headers = await _login(client)
        resp = await client.get("/api/observability/status", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is False
        assert body["reachable"] is False
        assert body["tracing_enabled"] is False


async def test_traces_returns_503_when_unconfigured():
    async with _client() as client:
        headers = await _login(client)
        resp = await client.get("/api/observability/traces", headers=headers)
        assert resp.status_code == 503


async def test_traces_requires_auth():
    async with _client() as client:
        resp = await client.get("/api/observability/traces")
        assert resp.status_code == 401


class _FakeLangfuseClient:
    """Stands in for LangfuseApiClient — returns canned public-API payloads."""

    def __init__(self, base_url=None):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        pass

    async def get_health(self):
        return {"status": "OK"}

    async def list_traces(self, page=1, limit=25, user_id=None, session_id=None, tags=None):
        return {
            "data": [
                {
                    "id": "trace-1",
                    "timestamp": "2026-06-12T10:00:00.000Z",
                    "name": "agent-mode-run",
                    "userId": "seven",
                    "sessionId": "agent-mode-abc123",
                    "tags": ["agent-mode"],
                    "latency": 42.5,
                    "input": "fix the tests",
                    "output": {"exit_code": 0},
                }
            ],
            "meta": {"page": page, "limit": limit, "totalItems": 1, "totalPages": 1},
        }

    async def get_trace(self, trace_id):
        return {
            "id": trace_id,
            "name": "persona-chat",
            "userId": "locutus",
            "tags": ["persona-chat"],
            "input": "hello",
            "output": "resistance is futile",
            "observations": [
                {
                    "id": "obs-2",
                    "type": "GENERATION",
                    "name": "llm-chat",
                    "startTime": "2026-06-12T10:00:01.000Z",
                    "model": "google/gemma-4-e4b",
                    "usageDetails": {"input": 10, "output": 5},
                    "output": "resistance is futile",
                },
                {
                    "id": "obs-1",
                    "type": "SPAN",
                    "name": "persona-chat",
                    "startTime": "2026-06-12T10:00:00.000Z",
                },
            ],
        }


@pytest.fixture
def _configured_langfuse(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_public_key", "pk-lf-test")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk-lf-test")
    monkeypatch.setattr(settings, "langfuse_ui_url", "http://homelab:3052")
    monkeypatch.setattr(obs_router, "LangfuseApiClient", _FakeLangfuseClient)


async def test_traces_are_mapped_to_compact_shape(_configured_langfuse):
    async with _client() as client:
        headers = await _login(client)
        resp = await client.get("/api/observability/traces?tag=agent-mode", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        trace = body["items"][0]
        assert trace["persona"] == "seven"
        assert trace["session_id"] == "agent-mode-abc123"
        assert trace["latency_ms"] == 42500.0
        assert trace["ui_url"] == "http://homelab:3052/project/borg/traces/trace-1"


async def test_trace_detail_sorts_observations_chronologically(_configured_langfuse):
    async with _client() as client:
        headers = await _login(client)
        resp = await client.get("/api/observability/traces/trace-1", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert [o["id"] for o in body["observations"]] == ["obs-1", "obs-2"]
        gen = body["observations"][1]
        assert gen["model"] == "google/gemma-4-e4b"
        assert gen["usage"] == {"input": 10, "output": 5}


async def test_status_reports_reachable_with_fake_client(_configured_langfuse):
    async with _client() as client:
        headers = await _login(client)
        resp = await client.get("/api/observability/status", headers=headers)
        body = resp.json()
        assert body["configured"] is True
        assert body["reachable"] is True


def test_trace_ui_url_empty_without_ui_setting(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_ui_url", "")
    assert obs_service.trace_ui_url("x") is None
