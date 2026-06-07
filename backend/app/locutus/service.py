"""Service layer for Locutus module — persona, memory, evolution, and filesystem operations."""

import asyncio
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

import frontmatter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.locutus.models import (
    CharacterMemoryEntry,
    CharacterProfile,
    EvolutionBudget,
    ReasoningLog,
    SkillRecord,
)

logger = logging.getLogger(__name__)

# Default Locutus storage directory
DEFAULT_LOCUTUS_DIR = Path.home() / ".locutus"
DEFAULT_CHARACTER_PATH = DEFAULT_LOCUTUS_DIR / "Character.md"
DEFAULT_MEMORY_PATH = DEFAULT_LOCUTUS_DIR / "CharacterMemory.md"
DEFAULT_SKILLS_DIR = DEFAULT_LOCUTUS_DIR / "skills"
DEFAULT_PROJECT_MEMORY_DIR = DEFAULT_LOCUTUS_DIR / "ProjectMemory"
DEFAULT_KNOWLEDGE_DIR = DEFAULT_LOCUTUS_DIR / "Knowledge"


async def get_or_create_character_profile(db: AsyncSession) -> CharacterProfile:
    """Get the character profile, creating defaults if none exists."""
    result = await db.execute(select(CharacterProfile).limit(1))
    profile = result.scalar_one_or_none()
    if profile:
        return profile

    profile = CharacterProfile(
        content="# Locutus\n\nYou are Locutus, a persistent AI assistant with your own personality.\n",
        file_path=str(DEFAULT_CHARACTER_PATH),
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def create_character_memory(
    db: AsyncSession,
    title: str,
    content: str = "",
    category: str = "general",
) -> CharacterMemoryEntry:
    """Create a new character memory entry."""
    entry = CharacterMemoryEntry(title=title, content=content, category=category)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def create_reasoning_log(
    db: AsyncSession,
    title: str,
    trigger_description: str,
    proposed_solution: str,
    expected_outcome: str,
    trigger_action_id: int | None = None,
) -> ReasoningLog:
    """Create a new reasoning log entry."""
    log = ReasoningLog(
        title=title,
        trigger_description=trigger_description,
        proposed_solution=proposed_solution,
        expected_outcome=expected_outcome,
        trigger_action_id=trigger_action_id,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def get_or_create_budget(db: AsyncSession) -> EvolutionBudget:
    """Get the current budget, creating defaults if none exists. Resets weekly."""
    result = await db.execute(select(EvolutionBudget).order_by(EvolutionBudget.id.desc()).limit(1))
    budget = result.scalar_one_or_none()

    if not budget:
        budget = EvolutionBudget(
            max_skills_per_week=5,
            max_agents_per_week=5,
            week_start=datetime.now(timezone.utc),
        )
        db.add(budget)
        await db.commit()
        await db.refresh(budget)
        return budget

    now = datetime.now(timezone.utc)
    week_start = budget.week_start
    if week_start.tzinfo is None:
        week_start = week_start.replace(tzinfo=timezone.utc)

    if (now - week_start).days >= 7:
        budget.skills_created = 0
        budget.agents_created = 0
        budget.week_start = now
        budget.updated_at = now
        await db.commit()
        await db.refresh(budget)

    return budget


async def create_skill_record(
    db: AsyncSession,
    name: str,
    description: str,
    file_path: str,
    reasoning_log_id: int | None = None,
) -> SkillRecord:
    """Create a skill record after writing a SKILL.md file."""
    record = SkillRecord(
        name=name,
        description=description,
        file_path=file_path,
        reasoning_log_id=reasoning_log_id,
        status="active",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def update_character_profile(
    db: AsyncSession,
    content: str,
    file_path: str | None = None,
) -> CharacterProfile:
    """Update the character profile and write to filesystem."""
    result = await db.execute(select(CharacterProfile).limit(1))
    profile = result.scalar_one_or_none()
    if not profile:
        profile = CharacterProfile(content=content, file_path=file_path or str(DEFAULT_CHARACTER_PATH))
        db.add(profile)

    profile.content = content
    if file_path:
        profile.file_path = file_path
    profile.last_synced_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(profile)
    return profile


def _resolve_locutus_path(file_path: str | None, default_path: Path) -> Path:
    """Resolve a Locutus file path and require it to stay under ~/.locutus."""
    base = DEFAULT_LOCUTUS_DIR.expanduser().resolve()
    path = Path(file_path).expanduser().resolve() if file_path else default_path.expanduser().resolve()
    if base != path and base not in path.parents:
        raise ValueError("Locutus file paths must stay under ~/.locutus")
    return path


async def read_character_file(file_path: str | None = None) -> str:
    """Read Character.md from filesystem using python-frontmatter."""
    path = _resolve_locutus_path(file_path, DEFAULT_CHARACTER_PATH)
    if not path.exists():
        return ""

    def _read() -> str:
        post = frontmatter.load(path)
        return post.content

    return await asyncio.to_thread(_read)


async def write_character_file(content: str, file_path: str | None = None) -> str:
    """Write Character.md to filesystem using python-frontmatter."""
    path = _resolve_locutus_path(file_path, DEFAULT_CHARACTER_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    def _write():
        post = frontmatter.Post(content)
        post.metadata = {"title": "Locutus Character", "updated": datetime.now(timezone.utc).isoformat()}
        with open(path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))

    await asyncio.to_thread(_write)
    return str(path)


async def list_character_memories(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    search: str | None = None,
    category: str | None = None,
    archived: bool = False,
) -> dict:
    """List character memories with pagination and filtering."""
    page = max(1, page)
    size = max(1, min(100, size))

    query = select(CharacterMemoryEntry)

    if archived:
        query = query.where(CharacterMemoryEntry.is_archived == True)  # noqa: E712
    else:
        query = query.where(CharacterMemoryEntry.is_archived == False)  # noqa: E712

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            CharacterMemoryEntry.title.ilike(term)
            | CharacterMemoryEntry.content.ilike(term)
        )

    if category and category.strip():
        query = query.where(CharacterMemoryEntry.category == category.strip())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * size
    items_result = await db.execute(
        query.offset(offset).limit(size).order_by(CharacterMemoryEntry.created_at.desc())
    )
    items = list(items_result.scalars().all())

    pages = math.ceil(total / size) if total > 0 else 0

    return {"items": items, "total": total, "page": page, "size": size, "pages": pages}


async def archive_character_memory(db: AsyncSession, entry_id: int) -> CharacterMemoryEntry | None:
    """Soft-delete a character memory entry."""
    result = await db.execute(select(CharacterMemoryEntry).where(CharacterMemoryEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        return None

    entry.is_archived = True
    entry.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(entry)
    return entry


async def seed_default_data(db: AsyncSession) -> None:
    """Seed initial Locutus data if tables are empty."""
    result = await db.execute(select(func.count()).select_from(CharacterProfile))
    profile_count = result.scalar() or 0
    if profile_count == 0:
        await get_or_create_character_profile(db)

    result = await db.execute(select(func.count()).select_from(EvolutionBudget))
    budget_count = result.scalar() or 0
    if budget_count == 0:
        await get_or_create_budget(db)
