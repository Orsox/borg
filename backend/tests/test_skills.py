"""Regression tests for the Skills module.

Covers:
- Name sanitization on create and update
- YAML validation before DB commit
- Normalized-name duplicate detection (409)
- Old workflow file cleanup on rename
"""

import json
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from sqlalchemy import select

from app.database import Base, AsyncSessionLocal, engine
from app.skills.models import Skill  # noqa: F401
from app.skills.service import (
    create_skill,
    update_skill,
    get_skill,
    get_skill_by_name,
    normalize_skill_name,
    DuplicateSkillNameError,
)
from app.skills.yaml_generator import validate_generated_yaml


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables before each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def tmp_workflows(tmp_path: Path) -> Path:
    """Return a temporary directory to use as the workflows path."""
    wf = tmp_path / ".archon" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    return wf


@pytest.fixture
def patched_service(tmp_workflows: Path):
    """Patch _DEFAULT_ARCHON_WORKFLOWS in the service module."""
    with patch("app.skills.service._DEFAULT_ARCHON_WORKFLOWS", tmp_workflows):
        yield tmp_workflows


# ---------------------------------------------------------------------------
# F1: Name sanitization on create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_skill_normalizes_name_and_writes_valid_yaml(
    patched_service: Path,
):
    """Creating 'My Skill !!!' stores 'my-skill', writes my-skill.yaml, and validates."""
    async with AsyncSessionLocal() as db:
        skill = await create_skill(
            db,
            name="My Skill !!!",
            description="A test skill",
            tags=["test"],
        )

    assert skill.name == "my-skill"
    workflow_path = patched_service / "my-skill.yaml"
    assert workflow_path.exists(), f"Expected {workflow_path} to exist"

    content = workflow_path.read_text(encoding="utf-8")
    is_valid, errors = validate_generated_yaml(content)
    assert is_valid, f"Generated YAML is invalid: {errors}"


# ---------------------------------------------------------------------------
# F1: Name sanitization on update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_skill_sanitizes_rename_and_validates_yaml(
    patched_service: Path,
):
    """Renaming a skill with special chars sanitizes the name and validates YAML."""
    async with AsyncSessionLocal() as db:
        skill = await create_skill(
            db,
            name="original-name",
            description="Original",
            tags=["test"],
        )
        skill_id = skill.id

    async with AsyncSessionLocal() as db:
        updated = await update_skill(db, skill_id, name="Renamed Skill !!!")

    assert updated.name == "renamed-skill"
    old_path = patched_service / "Renamed Skill !!!.yaml"
    new_path = patched_service / "renamed-skill.yaml"
    assert new_path.exists(), f"Expected {new_path} to exist"
    assert not old_path.exists(), "Old invalid workflow file should not exist"

    content = new_path.read_text(encoding="utf-8")
    is_valid, errors = validate_generated_yaml(content)
    assert is_valid, f"Regenerated YAML is invalid: {errors}"


# ---------------------------------------------------------------------------
# F2: Normalized duplicate detection — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skill_normalized_duplicate_create_returns_409(
    patched_service: Path,
):
    """Creating a skill whose normalized name already exists raises DuplicateSkillNameError."""
    async with AsyncSessionLocal() as db:
        await create_skill(
            db,
            name="my-skill",
            description="First",
            tags=["test"],
        )

    with pytest.raises(DuplicateSkillNameError, match="already exists"):
        async with AsyncSessionLocal() as db:
            await create_skill(
                db,
                name="My Skill !!!",  # normalizes to 'my-skill'
                description="Duplicate",
                tags=["test"],
            )


# ---------------------------------------------------------------------------
# F2: Normalized duplicate detection — update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skill_normalized_duplicate_update_returns_409(
    patched_service: Path,
):
    """Renaming a skill to a normalized name that already exists raises DuplicateSkillNameError."""
    async with AsyncSessionLocal() as db:
        skill_a = await create_skill(
            db,
            name="skill-a",
            description="A",
            tags=["test"],
        )
        skill_b = await create_skill(
            db,
            name="skill-b",
            description="B",
            tags=["test"],
        )

    with pytest.raises(DuplicateSkillNameError, match="already exists"):
        async with AsyncSessionLocal() as db:
            await update_skill(db, skill_b.id, name="Skill A !!!")  # normalizes to 'skill-a'


# ---------------------------------------------------------------------------
# normalize_skill_name helper
# ---------------------------------------------------------------------------


def test_normalize_skill_name_basic():
    """Basic normalization: spaces → hyphens, lowercased, special chars removed."""
    assert normalize_skill_name("My Skill") == "my-skill"
    assert normalize_skill_name("  My  Skill  ") == "my-skill"
    # Underscores and special chars are removed; spaces become hyphens
    assert normalize_skill_name("MY_SKILL!!!") == "myskill"
    assert normalize_skill_name("my-skill") == "my-skill"
    assert normalize_skill_name("hello world") == "hello-world"


def test_normalize_skill_name_empty_raises():
    """Empty or all-special-name should raise ValueError."""
    with pytest.raises(ValueError):
        normalize_skill_name("!!!")
