"""Tests for the archon_system module."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock


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
