"""Basic tests for BorgOS backend."""

import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test that the health endpoint returns correct shape."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "nominal"
        assert "uptime_seconds" in data
        assert "modules" in data
        assert data["modules"]["auth"] == "online"


@pytest.mark.asyncio
async def test_auth_login():
    """Test login with default credentials."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/token",
            data={"username": "borg", "password": "borgborg"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data


@pytest.mark.asyncio
async def test_auth_invalid_credentials():
    """Test login with wrong credentials returns 401."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/token",
            data={"username": "borg", "password": "wrongpassword"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_without_auth():
    """Test that protected endpoints require authentication."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/auth/me")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_note_crud():
    """Test note creation, retrieval, update, and deletion."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login
        login = await client.post(
            "/api/auth/token",
            data={"username": "borg", "password": "borgborg"},
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create note
        response = await client.post(
            "/api/brain/notes",
            json={"title": "Test Note", "content": "Hello [[World]]", "tags": ["test"]},
            headers=headers,
        )
        assert response.status_code == 201
        note = response.json()
        assert note["title"] == "Test Note"
        note_id = note["id"]

        # Get note
        response = await client.get(f"/api/brain/notes/{note_id}", headers=headers)
        assert response.status_code == 200

        # Update note
        response = await client.put(
            f"/api/brain/notes/{note_id}",
            json={"title": "Updated Note"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Note"

        # Archive note
        response = await client.delete(f"/api/brain/notes/{note_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["is_archived"] is True


@pytest.mark.asyncio
async def test_combined_graph():
    """Combined graph merges DB notes + action memory with namespaced IDs."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/auth/token",
            data={"username": "borg", "password": "borgborg"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # Two notes linked via a wiki-link, plus an action sharing a tag.
        # Beta first so Alpha's [[Beta]] resolves to an existing note.
        await client.post(
            "/api/brain/notes",
            json={"title": "Beta", "content": "leaf", "tags": ["shared"]},
            headers=headers,
        )
        await client.post(
            "/api/brain/notes",
            json={"title": "Alpha", "content": "see [[Beta]]", "tags": ["shared"]},
            headers=headers,
        )
        await client.post(
            "/api/brain/actions",
            json={"title": "Ran thing", "action_type": "test", "status": "success", "tags": ["shared"]},
            headers=headers,
        )

        resp = await client.get("/api/brain/graph/combined", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        ids = {n["id"] for n in data["nodes"]}
        sources = {n["source"] for n in data["nodes"]}
        assert any(i.startswith("note:") for i in ids)
        assert any(i.startswith("action:") for i in ids)
        assert {"note", "action"} <= sources
        # Wiki-link edge between the two notes, namespaced on both ends.
        assert any(
            e["source"].startswith("note:") and e["target"].startswith("note:")
            for e in data["edges"]
        )

        # link_tags=true adds cross-source bridges between note and action (shared tag).
        resp2 = await client.get("/api/brain/graph/combined?link_tags=true", headers=headers)
        edges2 = resp2.json()["edges"]
        assert len(edges2) > len(data["edges"])
        assert any(
            {e["source"].split(":")[0], e["target"].split(":")[0]} == {"note", "action"}
            for e in edges2
        )


@pytest.mark.asyncio
async def test_archon_failure_ingestion(tmp_path):
    """Failed Archon run logs are imported as failed ActionMemory entries, idempotently."""
    from app.database import AsyncSessionLocal
    from app.second_brain import action_service
    from app.second_brain.archon_ingest import ingest_archon_run_failures

    run_logs = tmp_path / "run-logs"
    run_logs.mkdir()
    (run_logs / "demo-fail.log").write_text(
        "Running workflow: demo\n"
        "❌\n"  # bare progress marker — must be ignored
        "❌ DAG workflow 'demo' completed with failures: 'n1': "
        "Node 'n1' failed: SDK returned error — The operation timed out.\n"
        "Error: Workflow failed: Workflow did not complete successfully\n",
        encoding="utf-8",
    )
    (run_logs / "demo-ok.log").write_text(
        '{"msg":"dag_workflow_finished","anyFailed":false}\nWorkflow completed\n',
        encoding="utf-8",
    )

    async with AsyncSessionLocal() as db:
        res = await ingest_archon_run_failures(db, archon_dir=tmp_path)
        assert res["created"] == 1  # only the failed log
        assert res["scanned"] == 2

        # Idempotent: a second pass creates nothing new.
        res2 = await ingest_archon_run_failures(db, archon_dir=tmp_path)
        assert res2["created"] == 0
        assert res2["skipped"] >= 1

        failed = await action_service.list_action_memories(db, status="failed")
        items = failed["items"]
        assert len(items) == 1
        entry = items[0]
        assert "demo-fail" in entry.title
        assert "timeout" in action_service._json_to_tags(entry.tags)


@pytest.mark.asyncio
async def test_user_create_and_list():
    """Test admin can create and list users."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/auth/token",
            data={"username": "borg", "password": "borgborg"},
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create user
        response = await client.post(
            "/api/users",
            json={"username": "testuser", "password": "testpass99"},
            headers=headers,
        )
        assert response.status_code == 201
        user = response.json()
        assert user["username"] == "testuser"
        assert user["is_admin"] is False

        # List users
        response = await client.get("/api/users", headers=headers)
        assert response.status_code == 200
        assert response.json()["total"] >= 2


@pytest.mark.asyncio
async def test_change_own_password():
    """Test user can change their own password."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/auth/token",
            data={"username": "borg", "password": "borgborg"},
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post(
            "/api/auth/me/change-password",
            json={"current_password": "borgborg", "new_password": "newpassword1"},
            headers=headers,
        )
        assert response.status_code == 204

        # Revert
        login2 = await client.post(
            "/api/auth/token",
            data={"username": "borg", "password": "newpassword1"},
        )
        token2 = login2.json()["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}"}
        await client.post(
            "/api/auth/me/change-password",
            json={"current_password": "newpassword1", "new_password": "borgborg"},
            headers=headers2,
        )


@pytest.mark.asyncio
async def test_non_admin_cannot_create_user():
    """Test regular users cannot access admin endpoints."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create non-admin user first using admin
        admin_login = await client.post(
            "/api/auth/token",
            data={"username": "borg", "password": "borgborg"},
        )
        admin_token = admin_login.json()["access_token"]
        await client.post(
            "/api/users",
            json={"username": "nonadmin", "password": "password99"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Login as non-admin
        login = await client.post(
            "/api/auth/token",
            data={"username": "nonadmin", "password": "password99"},
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post(
            "/api/users",
            json={"username": "anotheruser", "password": "password99"},
            headers=headers,
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_me_returns_is_admin():
    """Test GET /api/auth/me includes is_admin field."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/auth/token",
            data={"username": "borg", "password": "borgborg"},
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.get("/api/auth/me", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "is_admin" in data
        assert data["is_admin"] is True
        assert "is_active" in data


@pytest.mark.asyncio
async def test_task_crud():
    """Test task creation, retrieval, and deletion."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login
        login = await client.post(
            "/api/auth/token",
            data={"username": "borg", "password": "borgborg"},
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create task
        response = await client.post(
            "/api/tasks",
            json={
                "name": "Test Task",
                "task_type": "shell",
                "command": "echo hello",
                "tags": ["test"],
            },
            headers=headers,
        )
        assert response.status_code == 201
        task = response.json()
        assert task["name"] == "Test Task"
        task_id = task["id"]

        # Get task
        response = await client.get(f"/api/tasks/{task_id}", headers=headers)
        assert response.status_code == 200

        # Delete task
        response = await client.delete(f"/api/tasks/{task_id}", headers=headers)
        assert response.status_code == 200
