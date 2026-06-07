"""Tests for Locutus skill creation from approved proposals (Stage 4 of the
autonomy transition plan).

Covers:
- An approved ReasoningLog drafts exactly one skill YAML on disk + a draft
  SkillRecord with the correct reasoning_log_id FK + ReasoningLog.created_skill_path
- Validation failure leaves the ReasoningLog "approved" (not silently advanced),
  writes no file/SkillRecord, and is recorded as a LocutusAuditEntry(result="error")
- skill_drafted / skill_draft_failed Discord notification formatting
- End-to-end: gap analysis -> approval -> skill file + SkillRecord + notification,
  traceable via LocutusAuditEntry
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.locutus import gap_analysis
from app.locutus import service as locutus_service
from app.locutus.models import LocutusAuditEntry, ReasoningLog, SkillRecord
from app.second_brain.action_models import ActionMemory


async def _login_headers(client: AsyncClient) -> dict:
    login = await client.post("/api/auth/token", data={"username": "borg", "password": "borgborg"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _make_draft(title: str = "Recurring failures in 'thing'") -> ReasoningLog:
    async with AsyncSessionLocal() as db:
        return await locutus_service.create_reasoning_log(
            db,
            title=title,
            trigger_description="Recurring failure pattern detected.",
            proposed_solution="Create a skill that retries the failing step with backoff.",
            expected_outcome="Fewer recurring failures.",
        )


async def _get_log(log_id: int) -> ReasoningLog:
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(ReasoningLog).where(ReasoningLog.id == log_id))).scalar_one()


async def _skill_records_for(log_id: int) -> list[SkillRecord]:
    async with AsyncSessionLocal() as db:
        return list(
            (await db.execute(select(SkillRecord).where(SkillRecord.reasoning_log_id == log_id)))
            .scalars()
            .all()
        )


async def _audit_entries(action: str, target: str) -> list[LocutusAuditEntry]:
    async with AsyncSessionLocal() as db:
        return list(
            (
                await db.execute(
                    select(LocutusAuditEntry)
                    .where(LocutusAuditEntry.action == action)
                    .where(LocutusAuditEntry.target == target)
                    .order_by(LocutusAuditEntry.created_at.asc())
                )
            )
            .scalars()
            .all()
        )


@pytest.fixture(autouse=True)
def _skills_dir(tmp_path, monkeypatch):
    """Redirect generated skill YAML files to a temp dir instead of ~/.locutus/skills."""
    skills_dir = tmp_path / "skills"
    monkeypatch.setattr(locutus_service, "DEFAULT_SKILLS_DIR", skills_dir)
    return skills_dir


async def _approve(log_id: int) -> dict:
    transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = await _login_headers(client)
        resp = await client.post(
            f"/api/locutus/reasoning/{log_id}/decision",
            json={"decision": "approve"},
            headers=headers,
        )
    return {"status_code": resp.status_code, "body": resp.json()}


# ---------------------------------------------------------------------------
# Successful skill drafting on approval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approving_drafts_skill_file_and_record(_skills_dir):
    log = await _make_draft("Recurring failures in 'presentation_creation'")

    result = await _approve(log.id)
    assert result["status_code"] == 200
    assert result["body"]["status"] == "approved"

    refreshed = await _get_log(log.id)
    assert refreshed.status == "approved"
    assert refreshed.created_skill_path

    skill_path = list(_skills_dir.glob("*.yaml"))
    assert len(skill_path) == 1
    assert skill_path[0].read_text()  # non-empty YAML on disk
    assert refreshed.created_skill_path == str(skill_path[0])

    records = await _skill_records_for(log.id)
    assert len(records) == 1
    record = records[0]
    assert record.status == "draft"
    assert record.reasoning_log_id == log.id
    assert record.file_path == str(skill_path[0])

    entries = await _audit_entries("skill_creation", str(record.id))
    assert len(entries) == 1
    assert entries[0].result == "ok"
    assert f"proposal #{log.id}" in entries[0].payload_summary


@pytest.mark.asyncio
async def test_skill_draft_does_not_consume_extra_budget(_skills_dir):
    """Skill drafting itself doesn't touch EvolutionBudget — only the approval decision does."""
    async with AsyncSessionLocal() as db:
        budget_before = await locutus_service.get_or_create_budget(db)
        skills_before = budget_before.skills_created

    log = await _make_draft("Recurring failures in 'note_search'")
    await _approve(log.id)

    async with AsyncSessionLocal() as db:
        budget_after = await locutus_service.get_or_create_budget(db)

    assert budget_after.skills_created == skills_before + 1


# ---------------------------------------------------------------------------
# Validation failure path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_yaml_leaves_log_approved_and_writes_nothing(_skills_dir, monkeypatch):
    """If generated YAML fails validation, no file/SkillRecord is created and the
    ReasoningLog stays 'approved' — the failure is logged and notified, not silently
    swallowed or allowed to advance the log further."""

    def _fake_validate(_yaml_content):
        return False, ["Missing required field: nodes"]

    monkeypatch.setattr("app.skills.yaml_generator.validate_generated_yaml", _fake_validate)

    log = await _make_draft("Recurring failures in 'broken_thing'")
    result = await _approve(log.id)

    assert result["status_code"] == 200
    assert result["body"]["status"] == "approved"

    refreshed = await _get_log(log.id)
    assert refreshed.status == "approved"
    assert refreshed.created_skill_path is None

    assert list(_skills_dir.glob("*.yaml")) == []
    assert await _skill_records_for(log.id) == []

    entries = await _audit_entries("skill_creation", str(log.id))
    assert len(entries) == 1
    assert entries[0].result == "error"
    assert "validation failed" in entries[0].payload_summary.lower()


# ---------------------------------------------------------------------------
# Discord notification formatting
# ---------------------------------------------------------------------------


def test_format_skill_drafted_event():
    from app.discord_bot.listener import _format_skill_creation_event

    event = {
        "type": "skill_drafted",
        "skill_id": 5,
        "skill_name": "presentation-creation-failure-recovery-3",
        "reasoning_log_id": 3,
        "file_path": "/home/borg/.locutus/skills/presentation-creation-failure-recovery-3.yaml",
    }

    formatted = _format_skill_creation_event(event)

    assert formatted is not None
    assert "presentation-creation-failure-recovery-3" in formatted
    assert "#3" in formatted
    assert "/home/borg/.locutus/skills/" in formatted


def test_format_skill_draft_failed_event():
    from app.discord_bot.listener import _format_skill_creation_event

    event = {
        "type": "skill_draft_failed",
        "reasoning_log_id": 9,
        "error": "YAML validation failed for 'x-9': Missing required field: nodes",
    }

    formatted = _format_skill_creation_event(event)

    assert formatted is not None
    assert "#9" in formatted
    assert "Missing required field" in formatted


# ---------------------------------------------------------------------------
# End-to-end: gap analysis -> approval -> skill creation
# ---------------------------------------------------------------------------


def _make_failed_actions(action_type: str, count: int) -> list[ActionMemory]:
    now = datetime.now(timezone.utc)
    return [
        ActionMemory(
            title=f"{action_type} failure {i}",
            action_type=action_type,
            status="failed",
            created_at=now - timedelta(hours=i),
        )
        for i in range(count)
    ]


@pytest.fixture
def _stub_llm_drafting(monkeypatch):
    async def _fake_draft(gap, trigger_description):
        return f"Stubbed solution for {gap.action_type}"

    monkeypatch.setattr(gap_analysis, "_draft_proposed_solution", _fake_draft)


@pytest.mark.asyncio
async def test_end_to_end_gap_to_approved_skill(_skills_dir, _stub_llm_drafting):
    """Seed a repeating failure -> gap analysis drafts a proposal -> approving it
    via the API materializes a skill file + SkillRecord + notification, all
    traceable via LocutusAuditEntry."""
    actions = _make_failed_actions("data_export", count=4)

    async with AsyncSessionLocal() as db:
        for a in actions:
            db.add(a)
        await db.commit()

        proposals = await gap_analysis.run_gap_analysis(db, actions, run_id="e2e-test")

    assert len(proposals) == 1
    log = proposals[0]
    assert log.status == "draft"

    result = await _approve(log.id)
    assert result["status_code"] == 200
    assert result["body"]["status"] == "approved"

    refreshed = await _get_log(log.id)
    assert refreshed.created_skill_path

    records = await _skill_records_for(log.id)
    assert len(records) == 1
    assert records[0].status == "draft"

    skill_files = list(_skills_dir.glob("*.yaml"))
    assert len(skill_files) == 1

    # Traceable end-to-end via the audit trail: proposal -> decision -> creation
    proposal_entries = await _audit_entries("gap_analysis_proposal", str(log.id))
    decision_entries = await _audit_entries("reasoning_log_decision", str(log.id))
    creation_entries = await _audit_entries("skill_creation", str(records[0].id))
    assert len(proposal_entries) == 1
    assert len(decision_entries) == 1
    assert len(creation_entries) == 1
    assert creation_entries[0].result == "ok"
