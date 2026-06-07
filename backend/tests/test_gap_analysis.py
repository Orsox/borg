"""Tests for Locutus gap analysis (Stage 2 of the autonomy transition plan).

Covers:
- find_skill_gaps() surfaces recurring failure patterns by action_type
- run_gap_analysis() drafts exactly one ReasoningLog per gap, status="draft"
- run_gap_analysis() dedupes — running twice over the same data doesn't duplicate
- gap_analysis_completed Discord notification formatting
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.locutus import gap_analysis
from app.locutus.models import ReasoningLog
from app.second_brain.action_models import ActionMemory


def _make_actions(action_type: str, failed: int, succeeded: int = 0) -> list[ActionMemory]:
    now = datetime.now(timezone.utc)
    actions = []
    for i in range(failed):
        actions.append(
            ActionMemory(
                title=f"{action_type} failure {i}",
                action_type=action_type,
                status="failed",
                created_at=now - timedelta(hours=i),
            )
        )
    for i in range(succeeded):
        actions.append(
            ActionMemory(
                title=f"{action_type} success {i}",
                action_type=action_type,
                status="success",
                created_at=now - timedelta(hours=i),
            )
        )
    return actions


# ---------------------------------------------------------------------------
# find_skill_gaps
# ---------------------------------------------------------------------------


def test_find_skill_gaps_surfaces_action_types_above_threshold():
    """An action_type with >= GAP_FAILURE_THRESHOLD failures becomes a SkillGap."""
    actions = _make_actions("presentation_creation", failed=4, succeeded=2)
    actions += _make_actions("data_analysis", failed=1)

    gaps = gap_analysis.find_skill_gaps(actions)

    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.action_type == "presentation_creation"
    assert gap.failure_count == 4
    assert gap.suggested_skill_name
    assert gap.suggested_skill_description


def test_find_skill_gaps_ignores_action_types_below_threshold():
    actions = _make_actions("data_analysis", failed=2)

    assert gap_analysis.find_skill_gaps(actions) == []


# ---------------------------------------------------------------------------
# run_gap_analysis
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_llm_drafting(monkeypatch):
    """Avoid hitting LM Studio in tests — drafting is exercised separately."""

    async def _fake_draft(gap, trigger_description):
        return f"Stubbed solution for {gap.action_type}"

    monkeypatch.setattr(gap_analysis, "_draft_proposed_solution", _fake_draft)


async def _count_reasoning_logs() -> int:
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(func.count()).select_from(ReasoningLog))).scalar() or 0


@pytest.mark.asyncio
async def test_run_gap_analysis_creates_draft_reasoning_log():
    """A repeated failure pattern produces exactly one draft ReasoningLog with a non-empty proposal."""
    actions = _make_actions("presentation_creation", failed=4)

    async with AsyncSessionLocal() as db:
        for a in actions:
            db.add(a)
        await db.commit()

        created = await gap_analysis.run_gap_analysis(db, actions, run_id="test-run")

    assert len(created) == 1
    log = created[0]
    assert log.status == "draft"
    assert log.proposed_solution.strip() != ""
    assert log.expected_outcome.strip() != ""
    assert log.trigger_description.strip() != ""

    assert await _count_reasoning_logs() == 1


@pytest.mark.asyncio
async def test_run_gap_analysis_dedupes_across_runs():
    """Running gap analysis twice over the same recurring pattern doesn't duplicate the proposal."""
    actions = _make_actions("presentation_creation", failed=4)

    async with AsyncSessionLocal() as db:
        for a in actions:
            db.add(a)
        await db.commit()

        first = await gap_analysis.run_gap_analysis(db, actions, run_id="cycle-1")
        assert len(first) == 1

        second = await gap_analysis.run_gap_analysis(db, actions, run_id="cycle-2")
        assert second == []

    assert await _count_reasoning_logs() == 1


@pytest.mark.asyncio
async def test_run_gap_analysis_no_gaps_creates_nothing():
    actions = _make_actions("data_analysis", failed=1, succeeded=5)

    async with AsyncSessionLocal() as db:
        for a in actions:
            db.add(a)
        await db.commit()

        created = await gap_analysis.run_gap_analysis(db, actions)

    assert created == []
    assert await _count_reasoning_logs() == 0


# ---------------------------------------------------------------------------
# Discord notification formatting
# ---------------------------------------------------------------------------


def test_format_gap_analysis_event_lists_proposals():
    from app.discord_bot.listener import _format_gap_analysis_event

    event = {
        "type": "gap_analysis_completed",
        "run_id": 7,
        "proposals": [
            {"id": 1, "title": "Recurring failures in 'presentation_creation'", "trigger_description": "failed 4 times"},
        ],
    }

    formatted = _format_gap_analysis_event(event)

    assert formatted is not None
    assert "#1" in formatted
    assert "presentation_creation" in formatted
    assert "failed 4 times" in formatted


def test_format_gap_analysis_event_returns_none_when_no_proposals():
    from app.discord_bot.listener import _format_gap_analysis_event

    assert _format_gap_analysis_event({"type": "gap_analysis_completed", "run_id": 7, "proposals": []}) is None
