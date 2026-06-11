"""Regression tests for the Dreaming module.

Covers:
- top_categories sorting with archon:* tags (no KeyError)
- Full dreaming cycle with seeded ActionMemory and archon tags
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.database import Base, AsyncSessionLocal, engine
from app.second_brain.action_models import ActionMemory  # noqa: F401
from app.second_brain.models import Note  # noqa: F401
from app.dreaming.models import DreamingRun  # noqa: F401
from app.dreaming.service import _extract_patterns, run_dreaming_cycle
from app.task_automation.scheduler import translate_dreaming_config


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables and seed default user before each test."""
    from app.auth.service import seed_default_user

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        await seed_default_user(db)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ---------------------------------------------------------------------------
# F3: top_categories sort key with archon:* tags
# ---------------------------------------------------------------------------


def test_extract_patterns_sorts_archon_categories_by_count():
    """_extract_patterns() with repeated archon:* tags returns top_categories ordered by count."""
    actions = []
    for i in range(5):
        actions.append(
            ActionMemory(
                title=f"action {i}",
                action_type="archon_workflow",
                description=f"Workflow {i}",
                tags=json.dumps(["archon:review", "archon:analysis"]),
                status="success",
                created_at=datetime.now(timezone.utc) - timedelta(days=1),
                metadata_json=json.dumps({"errors": []}),
            )
        )
    for i in range(3):
        actions.append(
            ActionMemory(
                title=f"action {i+5}",
                action_type="archon_workflow",
                description=f"Workflow {i+5}",
                tags=json.dumps(["archon:review"]),
                status="failed",
                created_at=datetime.now(timezone.utc) - timedelta(days=2),
                metadata_json=json.dumps({"errors": ["timeout"]}),
            )
        )

    patterns = _extract_patterns(actions)
    top_cats = patterns["top_categories"]
    assert len(top_cats) > 0
    # "review" should have higher count than "analysis"
    review = next(c for c in top_cats if c["category"] == "review")
    analysis = next(c for c in top_cats if c["category"] == "analysis")
    assert review["count"] > analysis["count"]
    # Verify ordering: first item has highest count
    for i in range(len(top_cats) - 1):
        assert top_cats[i]["count"] >= top_cats[i + 1]["count"]


# ---------------------------------------------------------------------------
# Full dreaming cycle with archon tags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_dreaming_cycle_with_archon_tags_creates_note():
    """Seed ActionMemory rows with archon:* tags and errors, then confirm dreaming creates a note."""
    now = datetime.now(timezone.utc)

    # Seed 5 recent ActionMemory entries with archon:* tags
    async with AsyncSessionLocal() as db:
        for i in range(5):
            action = ActionMemory(
                title=f"archon action {i}",
                action_type="archon_workflow",
                description=f"Workflow borg-queen-{i}",
                tags=json.dumps(["archon:review", "archon:analysis"]),
                status="success" if i < 3 else "failed",
                created_at=now - timedelta(hours=i),
                metadata_json=json.dumps({"errors": ["timeout"]}) if i >= 3 else json.dumps({"errors": []}),
            )
            db.add(action)
        await db.commit()

    result = await run_dreaming_cycle(
        AsyncSessionLocal(),
        days=14,
        min_actions=1,  # lower threshold for testing
        persona="locutus",
    )

    assert result["status"] == "success"
    assert result["notes_created"] >= 1

    # Verify the DreamingRun record
    async with AsyncSessionLocal() as db:
        run = await db.execute(
            select(DreamingRun).order_by(DreamingRun.started_at.desc())
        )
        latest_run = run.scalar_one()
        assert latest_run.status == "success"
        assert latest_run.finished_at is not None
        assert latest_run.notes_created >= 1
        assert latest_run.action_memories_analyzed >= 5

        # Verify the Note was created in Second Brain
        note = await db.execute(
            select(Note).where(Note.title.contains("Dream Diary"))
        )
        created_note = note.scalar_one_or_none()
        assert created_note is not None


@pytest.mark.asyncio
async def test_run_dreaming_cycle_skips_when_insufficient_actions():
    """Dreaming returns 'skipped' when fewer than min_actions entries exist."""
    async with AsyncSessionLocal() as db:
        result = await run_dreaming_cycle(
            db,
            days=14,
            min_actions=100,  # way more than the 5 seeded entries
        )

    assert result["status"] == "skipped"


@pytest.mark.asyncio
async def test_manual_trigger_events_carry_persona():
    """Regression: run_task_now/_execute_task_now emittierten Task-Events ohne
    persona-Feld — Locutus verkündete Sevens Dreaming-Task statt Seven selbst."""
    import asyncio

    from app.task_automation.models import Task
    from app.task_automation.scheduler import sse_queue
    from app.task_automation.service import run_task_now

    # Queue leeren — andere Tests/Setup können Events hinterlassen haben
    while not sse_queue.empty():
        sse_queue.get_nowait()

    async with AsyncSessionLocal() as db:
        task = Task(
            name="Seven of Nine Dreaming Consolidation",
            task_type="dreaming",
            dreaming_days=14,
            dreaming_min_actions=5,
            dreaming_persona="seven",
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        run_id = await run_task_now(db, task.id)

    assert run_id is not None

    # task_run_started (sofort) + task_run_completed (Hintergrund) einsammeln
    events = {}
    for _ in range(10):
        try:
            event = await asyncio.wait_for(sse_queue.get(), timeout=5.0)
        except asyncio.TimeoutError:
            break
        if event.get("type", "").startswith("task_run_"):
            events[event["type"]] = event
        if "task_run_completed" in events or "task_run_failed" in events:
            break

    assert events["task_run_started"]["persona"] == "seven"
    done = events.get("task_run_completed") or events.get("task_run_failed")
    assert done is not None
    assert done["persona"] == "seven"


@pytest.mark.asyncio
async def test_scheduled_dreaming_task_does_not_self_deadlock():
    """Regression: _execute_task hielt eine offene Schreibtransaktion (TaskRun-
    INSERT nur geflusht, nicht committed), während der Dreaming-Zyklus in einer
    zweiten Session schreiben wollte — SQLite-Single-Writer-Self-Deadlock,
    jeder geplante Lauf endete mit "database is locked"."""
    from app.task_automation.models import Task, TaskRun
    from app.task_automation.scheduler import _execute_task

    async with AsyncSessionLocal() as db:
        task = Task(
            name="Seven of Nine Dreaming Consolidation",
            task_type="dreaming",
            dreaming_days=14,
            dreaming_min_actions=5,
            dreaming_persona="seven",
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_id = task.id

    await _execute_task(task_id)

    async with AsyncSessionLocal() as db:
        run = (
            await db.execute(select(TaskRun).where(TaskRun.task_id == task_id))
        ).scalars().first()

    assert run is not None
    assert run.status == "success"
    assert "database is locked" not in (run.stderr or "")


class TestTranslateDreamingConfig:
    """Tests for the human-friendly dreaming config translator."""

    def test_daily_at_0300(self):
        """Test: daily at 03:00 -> 0 3 * * *"""
        assert translate_dreaming_config("03:00", "daily") == "0 3 * * *"

    def test_hourly(self):
        """Test: hourly -> 0 * * * *"""
        assert translate_dreaming_config("03:00", "hourly") == "0 * * * *"

    def test_weekly(self):
        """Test: weekly at 03:00 -> 0 3 * * 0"""
        assert translate_dreaming_config("03:00", "weekly") == "0 3 * * 0"

    def test_every_6_hours(self):
        """Test: every_6_hours -> 0 */6 * * *"""
        assert translate_dreaming_config("03:00", "every_6_hours") == "0 */6 * * *"

    def test_every_12_hours(self):
        """Test: every_12_hours -> 0 */12 * * *"""
        assert translate_dreaming_config("03:00", "every_12_hours") == "0 */12 * * *"

    def test_invalid_time_format(self):
        """Test: invalid time format returns wildcard"""
        assert translate_dreaming_config("invalid", "daily") == "* * * * *"

    def test_custom_time(self):
        """Test: daily at 14:30 -> 30 14 * * *"""
        assert translate_dreaming_config("14:30", "daily") == "30 14 * * *"
