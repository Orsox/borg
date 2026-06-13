"""Tests for Seven's Sync Comparator Drone and the comparison run."""

import json
from contextlib import asynccontextmanager

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.peer_sync import service
from app.peer_sync.models import SyncItemRecord, SyncRun, PeerInstance
from app.seven_of_nine.models import DroneAuditEntry
from app.seven_of_nine.sync_agent import SyncComparatorDrone


async def test_drone_compare_produces_analysis_with_stub_chat():
    async def stub_chat(messages, system_prompt):
        # merge_recommendation expects a WINNER: line; others take free text.
        if "WINNER:" in messages[0]["content"]:
            return "WINNER: remote\nRemote ist aktueller."
        return "Unterschied festgestellt."

    drone = SyncComparatorDrone(stub_chat)
    analysis = await drone.compare("workflow", "workflows/a.yaml", "old", "new")

    assert analysis["semantic_summary"] == "Unterschied festgestellt."
    assert analysis["recommendation"]["winner"] == "remote"
    assert "aktueller" in analysis["recommendation"]["merge_notes"]
    assert analysis["risk"] == "Unterschied festgestellt."


async def test_run_comparison_writes_analysis_and_audit(monkeypatch):
    @asynccontextmanager
    async def fake_seven_chat():
        async def chat(messages, system_prompt):
            return "WINNER: local\nLokal bevorzugt."

        yield chat

    monkeypatch.setattr(service, "_seven_chat", fake_seven_chat)

    async with AsyncSessionLocal() as db:
        peer = PeerInstance(label="A", base_url="http://a", token="t")
        db.add(peer)
        await db.flush()
        run = SyncRun(peer_id=peer.id, status="diffed", counts_json="{}")
        db.add(run)
        await db.flush()
        item = SyncItemRecord(
            run_id=run.id,
            kind="skill",
            identity="skills/x.yaml",
            name="x",
            status="changed",
            local_content="a",
            remote_content="b",
        )
        db.add(item)
        await db.commit()
        run_id, item_id = run.id, item.id

    async with AsyncSessionLocal() as db:
        await service.run_comparison(db, run_id)

    async with AsyncSessionLocal() as db:
        refreshed = (
            await db.execute(select(SyncItemRecord).where(SyncItemRecord.id == item_id))
        ).scalar_one()
        analysis = json.loads(refreshed.analysis_json)
        assert analysis["recommendation"]["winner"] == "local"

        audits = (
            await db.execute(
                select(DroneAuditEntry).where(DroneAuditEntry.action == "peer_sync_compare")
            )
        ).scalars().all()
        assert len(audits) == 1
        assert audits[0].target == "skill:skills/x.yaml"

        run = (await db.execute(select(SyncRun).where(SyncRun.id == run_id))).scalar_one()
        assert run.status == "compared"
