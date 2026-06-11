"""Tests for Improvement Insights — generation, lifecycle, endpoints."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.second_brain.action_models import ActionMemory
from app.second_brain.insight_models import ImprovementInsight
from app.second_brain.insight_service import (
    generate_insights,
    get_top_insights,
    list_insights,
    set_status,
)


def _failed_action(
    title: str,
    category: str | None = "timeout",
    workflow: str = "borg-queen",
    description: str = "Error: The operation timed out.",
    hours_ago: int = 1,
) -> ActionMemory:
    tags = ["archon", workflow, "failed", "failure"]
    if category:
        tags.append(f"archon:{category}")
    return ActionMemory(
        title=title,
        description=description,
        action_type="archon_run",
        status="failed",
        tags=json.dumps(tags),
        metadata_json=json.dumps({"workflow": workflow, "category": category, "errors": []}),
        created_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )


async def _seed(actions: list[ActionMemory]) -> None:
    async with AsyncSessionLocal() as db:
        for a in actions:
            db.add(a)
        await db.commit()


@pytest.mark.asyncio
async def test_generate_groups_by_category_and_workflow():
    await _seed([
        _failed_action("t1", "timeout", "borg-queen", hours_ago=3),
        _failed_action("t2", "timeout", "borg-queen", hours_ago=2),
        _failed_action("w1", "worktree", "borg-drone", "Error: worktree is dirty", hours_ago=1),
    ])

    async with AsyncSessionLocal() as db:
        result = await generate_insights(db, days=14)
        assert result["created"] == 2
        assert result["updated"] == 0
        assert result["total_open"] == 2

        insights = (await db.execute(select(ImprovementInsight))).scalars().all()
        by_key = {i.dedup_key: i for i in insights}
        timeout = by_key["timeout:borg-queen"]
        assert timeout.occurrences == 2
        assert len(json.loads(timeout.evidence_refs)) == 2
        assert "timeouts" in timeout.recommendation or "timeout" in timeout.recommendation
        worktree = by_key["worktree:borg-drone"]
        assert worktree.occurrences == 1
        assert "worktree" in worktree.recommendation


@pytest.mark.asyncio
async def test_generate_is_idempotent():
    await _seed([_failed_action("t1"), _failed_action("t2", hours_ago=2)])

    async with AsyncSessionLocal() as db:
        first = await generate_insights(db, days=14)
        assert first["created"] == 1

    async with AsyncSessionLocal() as db:
        second = await generate_insights(db, days=14)
        assert second["created"] == 0
        assert second["updated"] == 0
        insight = (await db.execute(select(ImprovementInsight))).scalar_one()
        assert insight.occurrences == 2


@pytest.mark.asyncio
async def test_acknowledged_persists_resolved_reopens():
    await _seed([_failed_action("t1")])
    async with AsyncSessionLocal() as db:
        await generate_insights(db, days=14)
        insight = (await db.execute(select(ImprovementInsight))).scalar_one()

        # Acknowledged stays acknowledged through regeneration with new evidence.
        await set_status(db, insight.id, "acknowledged")
    await _seed([_failed_action("t2", hours_ago=0)])
    async with AsyncSessionLocal() as db:
        result = await generate_insights(db, days=14)
        assert result["updated"] == 1
        insight = (await db.execute(select(ImprovementInsight))).scalar_one()
        assert insight.status == "acknowledged"
        assert insight.occurrences == 2

        # Resolved reopens when newer evidence arrives (regression detection).
        await set_status(db, insight.id, "resolved")
    await _seed([_failed_action("t3", hours_ago=0)])
    async with AsyncSessionLocal() as db:
        await generate_insights(db, days=14)
        insight = (await db.execute(select(ImprovementInsight))).scalar_one()
        assert insight.status == "open"
        assert insight.occurrences == 3


@pytest.mark.asyncio
async def test_uncategorized_failures_fall_back():
    """Failures without category tags/metadata get categorized from text or 'uncategorized'."""
    action = ActionMemory(
        title="mystery",
        description="Something exploded for no documented reason",
        action_type="custom_thing",
        status="failed",
        tags=json.dumps([]),
        metadata_json=json.dumps({}),
        created_at=datetime.now(timezone.utc),
    )
    await _seed([action])

    async with AsyncSessionLocal() as db:
        await generate_insights(db, days=14)
        insight = (await db.execute(select(ImprovementInsight))).scalar_one()
        assert insight.category == "uncategorized"
        assert insight.workflow == "custom_thing"


@pytest.mark.asyncio
async def test_list_and_top_ordering():
    await _seed(
        [_failed_action(f"t{i}", "timeout", "borg-queen", hours_ago=i) for i in range(3)]
        + [_failed_action("w1", "worktree", "borg-drone", "Error: worktree is dirty")]
    )
    async with AsyncSessionLocal() as db:
        await generate_insights(db, days=14)

        top = await get_top_insights(db, limit=1)
        assert len(top) == 1
        assert top[0].dedup_key == "timeout:borg-queen"  # most occurrences first

        page = await list_insights(db, status="open", page=1, size=10)
        assert page["total"] == 2

        await set_status(db, top[0].id, "resolved")
        page = await list_insights(db, status="open", page=1, size=10)
        assert page["total"] == 1
        page_all = await list_insights(db, status="all", page=1, size=10)
        assert page_all["total"] == 2


@pytest.mark.asyncio
async def test_insight_endpoints():
    await _seed([_failed_action("t1"), _failed_action("t2", hours_ago=2)])

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/auth/token", data={"username": "borg", "password": "borgborg"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        resp = await client.post("/api/brain/insights/generate?days=14", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["created"] == 1

        resp = await client.get("/api/brain/insights?status=open", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        insight = data["items"][0]
        assert insight["category"] == "timeout"
        assert insight["occurrences"] == 2
        assert len(insight["evidence_action_ids"]) == 2

        resp = await client.get("/api/brain/insights/top?limit=3", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = await client.post(
            f"/api/brain/insights/{insight['id']}/acknowledge", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "acknowledged"

        resp = await client.post(
            f"/api/brain/insights/{insight['id']}/resolve", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"

        resp = await client.post("/api/brain/insights/99999/resolve", headers=headers)
        assert resp.status_code == 404

        # Resolved insights no longer appear in the default (open) listing.
        resp = await client.get("/api/brain/insights", headers=headers)
        assert resp.json()["total"] == 0

    # Unauthenticated access is rejected.
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/brain/insights")
        assert resp.status_code == 401
