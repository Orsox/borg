"""Tests for the Locutus approval gate (Stage 3 of the autonomy transition plan).

Covers:
- POST /api/locutus/reasoning/{id}/decision moves draft -> approved/rejected
- Every decision produces a LocutusAuditEntry with actor="user"
- EvolutionBudget is checked and decremented at approval time, not proposal time
- A budget-exhausted approval attempt is denied and leaves status="draft"
- GET /api/locutus/reasoning lists and filters by status
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.locutus import service as locutus_service
from app.locutus.models import EvolutionBudget, LocutusAuditEntry, ReasoningLog


async def _login_headers(client: AsyncClient) -> dict:
    login = await client.post("/api/auth/token", data={"username": "borg", "password": "borgborg"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _make_draft(title: str = "Draft proposal") -> ReasoningLog:
    async with AsyncSessionLocal() as db:
        return await locutus_service.create_reasoning_log(
            db,
            title=title,
            trigger_description="Recurring failure pattern detected.",
            proposed_solution="Create a skill that addresses the pattern.",
            expected_outcome="Fewer recurring failures.",
        )


async def _get_log(log_id: int) -> ReasoningLog:
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(select(ReasoningLog).where(ReasoningLog.id == log_id))
        ).scalar_one()


async def _get_budget() -> EvolutionBudget:
    async with AsyncSessionLocal() as db:
        return await locutus_service.get_or_create_budget(db)


async def _last_decision_entry(log_id: int) -> LocutusAuditEntry | None:
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                select(LocutusAuditEntry)
                .where(LocutusAuditEntry.action == "reasoning_log_decision")
                .where(LocutusAuditEntry.target == str(log_id))
                .order_by(LocutusAuditEntry.created_at.desc())
            )
        ).scalars().first()


@pytest.mark.asyncio
async def test_approve_transitions_status_and_increments_budget():
    log = await _make_draft("Approve me")
    budget_before = await _get_budget()
    skills_before = budget_before.skills_created

    transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login_headers(client)
        resp = await client.post(
            f"/api/locutus/reasoning/{log.id}/decision",
            json={"decision": "approve", "note": "looks good"},
            headers=headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"

    refreshed = await _get_log(log.id)
    assert refreshed.status == "approved"

    budget_after = await _get_budget()
    assert budget_after.skills_created == skills_before + 1

    entry = await _last_decision_entry(log.id)
    assert entry is not None
    assert entry.actor == "user"
    assert entry.result == "ok"
    assert "approve" in entry.payload_summary
    assert "looks good" in entry.payload_summary


@pytest.mark.asyncio
async def test_reject_transitions_status_without_touching_budget():
    log = await _make_draft("Reject me")
    budget_before = await _get_budget()
    skills_before = budget_before.skills_created

    transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login_headers(client)
        resp = await client.post(
            f"/api/locutus/reasoning/{log.id}/decision",
            json={"decision": "reject", "note": "not now"},
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    refreshed = await _get_log(log.id)
    assert refreshed.status == "rejected"

    budget_after = await _get_budget()
    assert budget_after.skills_created == skills_before

    entry = await _last_decision_entry(log.id)
    assert entry is not None
    assert entry.actor == "user"
    assert "reject" in entry.payload_summary


@pytest.mark.asyncio
async def test_decision_on_already_decided_log_is_rejected():
    log = await _make_draft("Decide twice")

    transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login_headers(client)
        first = await client.post(
            f"/api/locutus/reasoning/{log.id}/decision",
            json={"decision": "approve"},
            headers=headers,
        )
        assert first.status_code == 200

        second = await client.post(
            f"/api/locutus/reasoning/{log.id}/decision",
            json={"decision": "reject"},
            headers=headers,
        )

    assert second.status_code == 409
    refreshed = await _get_log(log.id)
    assert refreshed.status == "approved"


@pytest.mark.asyncio
async def test_decision_on_unknown_log_returns_404():
    transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login_headers(client)
        resp = await client.post(
            "/api/locutus/reasoning/999999/decision",
            json={"decision": "approve"},
            headers=headers,
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approval_denied_when_budget_exhausted():
    """Approving while skills_created >= max_skills_per_week errors and leaves status='draft'."""
    async with AsyncSessionLocal() as db:
        budget = await locutus_service.get_or_create_budget(db)
        budget.max_skills_per_week = 1
        budget.skills_created = 1
        await db.commit()

    log = await _make_draft("Over budget")

    transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login_headers(client)
        resp = await client.post(
            f"/api/locutus/reasoning/{log.id}/decision",
            json={"decision": "approve"},
            headers=headers,
        )

    assert resp.status_code == 429

    refreshed = await _get_log(log.id)
    assert refreshed.status == "draft"

    budget_after = await _get_budget()
    assert budget_after.skills_created == 1

    entry = await _last_decision_entry(log.id)
    assert entry is not None
    assert entry.actor == "user"
    assert entry.result == "denied"
    assert "budget" in entry.payload_summary.lower()


@pytest.mark.asyncio
async def test_list_reasoning_logs_filters_by_status():
    draft = await _make_draft("Listed draft")

    async with AsyncSessionLocal() as db:
        approved = await locutus_service.create_reasoning_log(
            db,
            title="Already approved",
            trigger_description="x",
            proposed_solution="y",
            expected_outcome="z",
        )
        approved.status = "approved"
        await db.commit()

    transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login_headers(client)
        resp = await client.get("/api/locutus/reasoning", params={"status": "draft"}, headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    ids = [item["id"] for item in body["items"]]
    assert draft.id in ids
    assert approved.id not in ids
    assert all(item["status"] == "draft" for item in body["items"])
