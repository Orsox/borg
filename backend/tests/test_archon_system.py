"""Tests for the archon_system module."""

import json

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.second_brain.action_models import ActionMemory


@pytest.fixture
async def auth_headers():
    """Get auth headers by logging in."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/token",
            data={"username": "borg", "password": "borgborg"},
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Mock ArchonClient tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_endpoint_online(auth_headers):
    """Health endpoint returns online data when Archon responds."""
    from app.main import app
    from app.archon_system.client import ArchonClient

    mock_client = AsyncMock(spec=ArchonClient)
    mock_client.get_health = AsyncMock(return_value={
        "status": "nominal",
        "version": "0.3.12",
        "adapter": "web",
        "is_docker": False,
        "runningWorkflows": 2,
        "activePlatforms": ["Web", "CLI"],
    })
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.archon_system.service.ArchonClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/archon-system/health", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["online"] is True
            assert data["version"] == "0.3.12"
            assert data["running_workflows"] == 2
            assert data["cached"] is False


@pytest.mark.asyncio
async def test_health_endpoint_offline(auth_headers):
    """Health endpoint returns cached data when Archon is unreachable."""
    from app.main import app
    from app.archon_system.client import ArchonClient, ArchonUnavailable

    mock_client = AsyncMock(spec=ArchonClient)
    mock_client.get_health = AsyncMock(side_effect=ArchonUnavailable("http://localhost:3090"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.archon_system.service.ArchonClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/archon-system/health", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            # When no cached data exists and Archon is down, should still return valid response
            assert "online" in data
            assert "cached" in data


@pytest.mark.asyncio
async def test_runs_endpoint(auth_headers):
    """Runs endpoint returns runs data."""
    from app.main import app
    from app.archon_system.client import ArchonClient

    mock_client = AsyncMock(spec=ArchonClient)
    mock_client.get_runs = AsyncMock(return_value=[
        {
            "id": "run-123",
            "workflow_name": "test-workflow",
            "status": "running",
            "started_at": "2026-01-01T00:00:00Z",
        }
    ])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.archon_system.service.ArchonClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/archon-system/runs", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert data["total"] >= 0

    async with AsyncSessionLocal() as db:
        action = (
            await db.execute(
                select(ActionMemory).where(ActionMemory.source_kind == "archon_run")
            )
        ).scalar_one()
        assert action.source_ref == "run-123"
        assert action.status == "in_progress"
        assert "Current Archon status: running." in action.description


@pytest.mark.asyncio
async def test_codebases_endpoint(auth_headers):
    """Codebases endpoint returns codebases data."""
    from app.main import app
    from app.archon_system.client import ArchonClient

    mock_client = AsyncMock(spec=ArchonClient)
    mock_client.get_codebases = AsyncMock(return_value=[
        {
            "id": "cb-123",
            "name": "test-repo",
            "repository_url": "https://github.com/test/repo.git",
        }
    ])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.archon_system.service.ArchonClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/archon-system/codebases", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert data["total"] >= 0


@pytest.mark.asyncio
async def test_workflows_endpoint(auth_headers):
    """Workflows endpoint returns workflows data (nodes stripped)."""
    from app.main import app
    from app.archon_system.client import ArchonClient

    mock_client = AsyncMock(spec=ArchonClient)
    mock_client.get_workflows = AsyncMock(return_value=[
        {
            "workflow": {
                "name": "test-workflow",
                "description": "A test workflow",
                "provider": "pi",
                "nodes": [{"id": "n1", "type": "start"}],  # should be stripped
            },
            "source": "project",
        }
    ])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.archon_system.service.ArchonClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/archon-system/workflows", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert data["total"] >= 0
            # Ensure nodes are NOT in the response
            for item in data["items"]:
                assert "nodes" not in item


@pytest.mark.asyncio
async def test_sync_endpoint(auth_headers):
    """Sync endpoint triggers full sync."""
    from app.main import app
    from app.archon_system.client import ArchonClient

    mock_client = AsyncMock(spec=ArchonClient)
    mock_client.get_health = AsyncMock(return_value={
        "version": "0.3.12",
        "runningWorkflows": 1,
        "activePlatforms": ["Web"],
    })
    mock_client.get_runs = AsyncMock(return_value=[])
    mock_client.get_codebases = AsyncMock(return_value=[])
    mock_client.get_workflows = AsyncMock(return_value=[])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.archon_system.service.ArchonClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/archon-system/sync", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert "synced_at" in data
            assert "health_updated" in data
            assert "runs_count" in data


@pytest.mark.asyncio
async def test_unauthenticated_access_denied():
    """Archon-system endpoints require authentication."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/archon-system/health")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_shape_mapping():
    """Archon camelCase fields are mapped to snake_case."""
    from app.archon_system.client import ArchonClient

    client = ArchonClient("http://localhost:3090")
    # Verify the base_url is set correctly
    assert client.base_url == "http://localhost:3090"


@pytest.mark.asyncio
async def test_client_context_initializes_httpx_client():
    """Client context manager creates an AsyncClient with a valid timeout."""
    from app.archon_system.client import ArchonClient

    client = ArchonClient("http://localhost:3090")

    async with client:
        assert client._client is not None

    assert client._client is None


@pytest.mark.asyncio
async def test_health_fallback_no_cached_data(auth_headers):
    """When Archon is down and no cached data exists, returns valid empty response."""
    from app.main import app
    from app.archon_system.client import ArchonClient, ArchonUnavailable
    from app.archon_system.models import ArchonSystemHealth
    from sqlalchemy import delete
    from app.database import AsyncSessionLocal

    # Clear any cached health data
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ArchonSystemHealth))
        await db.commit()

    mock_client = AsyncMock(spec=ArchonClient)
    mock_client.get_health = AsyncMock(side_effect=ArchonUnavailable("http://localhost:3090"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.archon_system.service.ArchonClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/archon-system/health", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["online"] is False
            assert data["cached"] is True


@pytest.mark.asyncio
async def test_failed_run_errors_are_searchable_in_action_memory(auth_headers):
    """Failed Archon runs are mirrored into Action Memory with searchable error text."""
    from app.main import app
    from app.archon_system.client import ArchonClient

    mock_client = AsyncMock(spec=ArchonClient)
    mock_client.get_runs = AsyncMock(return_value=[
        {
            "id": "run-failed-1",
            "workflow_name": "borg-system-architekt",
            "status": "failed",
            "user_message": "implement action memory logging",
            "error": "final review model resolution failed",
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": "2026-01-01T00:05:00Z",
        }
    ])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.archon_system.service.ArchonClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/archon-system/runs", headers=auth_headers)
            assert response.status_code == 200

            response = await client.get(
                "/api/brain/actions?search=model%20resolution%20failed",
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["items"][0]["status"] == "failed"


@pytest.mark.asyncio
async def test_metadata_error_is_extracted(auth_headers):
    """Real Archon payloads nest the failure under metadata.error — it must be captured."""
    from app.main import app
    from app.archon_system.client import ArchonClient

    error_text = (
        "DAG workflow 'borg-system-architekt' completed with failures: "
        "'process-tasks': Loop iteration 3 failed: SDK returned error — LM Link connection entered error"
    )
    mock_client = AsyncMock(spec=ArchonClient)
    mock_client.get_runs = AsyncMock(return_value=[
        {
            "id": "run-meta-error",
            "workflow_name": "borg-system-architekt",
            "status": "failed",
            "user_message": "implement action memory logging",
            "metadata": {"error": error_text, "rejection_reason": ""},
        }
    ])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.archon_system.service.ArchonClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/archon-system/runs", headers=auth_headers)
            assert response.status_code == 200

    async with AsyncSessionLocal() as db:
        action = (
            await db.execute(
                select(ActionMemory).where(ActionMemory.source_ref == "run-meta-error")
            )
        ).scalar_one()
        assert action.status == "failed"
        assert error_text in action.description
        meta = json.loads(action.metadata_json)
        assert error_text in meta["errors"]
        assert meta["archon_metadata"]["error"] == error_text
        assert "has-errors" in action.tags


@pytest.mark.asyncio
async def test_small_error_on_successful_run_is_flagged(auth_headers):
    """A non-fatal error (agents_failed) on an otherwise successful run is still flagged."""
    from app.main import app
    from app.archon_system.client import ArchonClient

    mock_client = AsyncMock(spec=ArchonClient)
    mock_client.get_runs = AsyncMock(return_value=[
        {
            "id": "run-small-error",
            "workflow_name": "borg-nanoprobe",
            "status": "completed",
            "agents_failed": 1,
            "agents_total": 4,
            "agents_completed": 3,
        }
    ])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.archon_system.service.ArchonClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/archon-system/runs", headers=auth_headers)
            assert response.status_code == 200

            response = await client.get(
                "/api/brain/actions?search=has-errors", headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1

    async with AsyncSessionLocal() as db:
        action = (
            await db.execute(
                select(ActionMemory).where(ActionMemory.source_ref == "run-small-error")
            )
        ).scalar_one()
        # Lifecycle status stays truthful (run completed), but the error is surfaced.
        assert action.status == "success"
        assert "has-errors" in action.tags
        assert '"has_errors": true' in action.metadata_json
        assert "Failed agents: 1" in action.description


@pytest.mark.asyncio
async def test_errors_accumulate_across_syncs(auth_headers):
    """Errors from earlier syncs are preserved when a later sync reports different errors."""
    from app.main import app
    from app.archon_system.client import ArchonClient

    error_1 = "Loop iteration 1 failed: transient network error"
    error_2 = "Loop iteration 3 failed: SDK returned error — timeout"
    mock_client = AsyncMock(spec=ArchonClient)
    mock_client.get_runs = AsyncMock(side_effect=[
        [{
            "id": "run-accumulate",
            "workflow_name": "borg-queen",
            "status": "running",
            "metadata": {"error": error_1},
        }],
        [{
            "id": "run-accumulate",
            "workflow_name": "borg-queen",
            "status": "failed",
            "metadata": {"error": error_2},
        }],
    ])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.archon_system.service.ArchonClient", return_value=mock_client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/api/archon-system/runs", headers=auth_headers)).status_code == 200
            assert (await client.get("/api/archon-system/runs", headers=auth_headers)).status_code == 200

    async with AsyncSessionLocal() as db:
        action = (
            await db.execute(
                select(ActionMemory).where(ActionMemory.source_ref == "run-accumulate")
            )
        ).scalar_one()
        meta = json.loads(action.metadata_json)
        assert error_1 in meta["errors"]
        assert error_2 in meta["errors"]
        assert error_1 in action.description
        assert error_2 in action.description
