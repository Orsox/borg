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
    LocutusAuditEntry,
    ReasoningLog,
    SkillRecord,
)

logger = logging.getLogger(__name__)


class ReasoningLogNotFound(Exception):
    """Raised when a decision targets a ReasoningLog id that doesn't exist."""


class ReasoningLogNotDraft(Exception):
    """Raised when a decision targets a ReasoningLog that has already been decided."""


class EvolutionBudgetExhausted(Exception):
    """Raised when approving would exceed the weekly skill-creation budget."""


class SkillDraftError(Exception):
    """Raised when generating a skill from an approved ReasoningLog fails validation."""

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
    await record_action(
        db,
        action="character_memory_create",
        target=str(entry.id),
        payload_summary=entry.title,
    )
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


async def list_reasoning_logs(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    status: str | None = None,
) -> dict:
    """List reasoning logs newest-first, paginated and optionally filtered by status."""
    page = max(1, page)
    size = max(1, min(100, size))

    query = select(ReasoningLog)
    if status and status.strip():
        query = query.where(ReasoningLog.status == status.strip())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * size
    items_result = await db.execute(
        query.offset(offset).limit(size).order_by(ReasoningLog.created_at.desc())
    )
    items = list(items_result.scalars().all())

    pages = math.ceil(total / size) if total > 0 else 0

    return {"items": items, "total": total, "page": page, "size": size, "pages": pages}


async def decide_reasoning_log(
    db: AsyncSession,
    log_id: int,
    decision: str,
    note: str | None = None,
) -> ReasoningLog:
    """Move a draft `ReasoningLog` to `approved`/`rejected` — the sole human decision point.

    This is the only code path allowed to write `status="approved"`/`"rejected"`
    (per the ADVISOR boundary in the autonomy plan). Approval checks and decrements
    the weekly `EvolutionBudget` *here*, not at proposal time, so drafts never
    consume budget — only acted-upon proposals do. Every decision (including a
    budget-denied approval attempt) produces a `LocutusAuditEntry` with `actor="user"`.
    """
    result = await db.execute(select(ReasoningLog).where(ReasoningLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise ReasoningLogNotFound(f"ReasoningLog {log_id} not found")

    if log.status != "draft":
        raise ReasoningLogNotDraft(
            f"ReasoningLog {log_id} already decided (status={log.status})"
        )

    summary = f"{decision}" + (f" — {note}" if note else "")

    if decision == "approve":
        budget = await get_or_create_budget(db)
        if budget.skills_created >= budget.max_skills_per_week:
            await record_action(
                db,
                actor="user",
                action="reasoning_log_decision",
                target=str(log.id),
                payload_summary=f"approve denied — evolution budget exhausted "
                f"({budget.skills_created}/{budget.max_skills_per_week})",
                result="denied",
            )
            raise EvolutionBudgetExhausted(
                f"Weekly skill-creation budget exhausted "
                f"({budget.skills_created}/{budget.max_skills_per_week})"
            )

        budget.skills_created += 1
        budget.updated_at = datetime.now(timezone.utc)
        log.status = "approved"
    else:
        log.status = "rejected"

    log.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(log)

    await record_action(
        db,
        actor="user",
        action="reasoning_log_decision",
        target=str(log.id),
        payload_summary=summary,
    )

    if decision == "approve":
        # Stage 4: close the loop — an approved proposal drafts a skill file
        # immediately (creation, not execution). Validation failures are recorded
        # and notified but never bubble up to fail the approval response — the
        # ReasoningLog stays "approved" either way.
        try:
            await draft_skill_from_reasoning_log(db, log, run_id=f"reasoning-{log.id}")
        except SkillDraftError:
            pass
        except Exception:
            logger.exception(f"Skill drafting failed for ReasoningLog #{log.id}")

    return log


async def draft_skill_from_reasoning_log(
    db: AsyncSession,
    log: ReasoningLog,
    run_id: str | None = None,
) -> SkillRecord:
    """Generate, validate, and persist a skill drafted from an approved ReasoningLog.

    Stage 4 of the autonomy plan — closes the loop from human-approved proposal to
    a `status="draft"` `SkillRecord` + skill YAML on disk, with no execution. The
    skill remains `draft` until a human promotes it elsewhere (out of scope here).

    On YAML validation failure: no file is written, no `SkillRecord` is created,
    the failure is recorded as a `LocutusAuditEntry` with `result="error"`, a
    `skill_draft_failed` SSE event is emitted for Discord, and `SkillDraftError`
    is raised so the caller knows nothing was persisted.
    """
    from app.skills.service import normalize_skill_name
    from app.skills.yaml_generator import generate_skill_yaml, validate_generated_yaml
    from app.task_automation.scheduler import sse_queue

    skill_name = f"{normalize_skill_name(log.title)}-{log.id}"
    description = f"{log.proposed_solution}\n\nExpected outcome: {log.expected_outcome}"

    yaml_content = generate_skill_yaml(
        name=skill_name,
        description=description,
        category="autonomous",
        tags=["auto-generated", f"reasoning-log-{log.id}"],
    )

    is_valid, errors = validate_generated_yaml(yaml_content)
    if not is_valid:
        error_summary = f"YAML validation failed for '{skill_name}': {'; '.join(errors)}"
        await record_action(
            db,
            action="skill_creation",
            target=str(log.id),
            payload_summary=error_summary,
            result="error",
            run_id=run_id,
        )
        await sse_queue.put({
            "type": "skill_draft_failed",
            "reasoning_log_id": log.id,
            "error": error_summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        raise SkillDraftError(error_summary)

    DEFAULT_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = DEFAULT_SKILLS_DIR / f"{skill_name}.yaml"
    await asyncio.to_thread(file_path.write_text, yaml_content, encoding="utf-8")

    record = await create_skill_record(
        db,
        name=skill_name,
        description=description,
        file_path=str(file_path),
        reasoning_log_id=log.id,
        status="draft",
    )

    log.created_skill_path = str(file_path)
    log.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(log)

    await record_action(
        db,
        action="skill_creation",
        target=str(record.id),
        payload_summary=f"Drafted skill '{skill_name}' from proposal #{log.id} -> {file_path}",
        run_id=run_id,
    )

    await sse_queue.put({
        "type": "skill_drafted",
        "skill_id": record.id,
        "skill_name": record.name,
        "reasoning_log_id": log.id,
        "file_path": str(file_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return record


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
    status: str = "draft",
) -> SkillRecord:
    """Create a skill record after writing a skill file. Defaults to `status="draft"` —
    a generated skill is never auto-promoted to `active` (see Stage 4 of the autonomy plan)."""
    record = SkillRecord(
        name=name,
        description=description,
        file_path=file_path,
        reasoning_log_id=reasoning_log_id,
        status=status,
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
    await record_action(
        db,
        action="character_memory_archive",
        target=str(entry.id),
        payload_summary=entry.title,
    )
    return entry


async def record_action(
    db: AsyncSession,
    *,
    action: str,
    actor: str = "locutus",
    target: str | None = None,
    payload_summary: str | None = None,
    result: str = "ok",
    run_id: str | None = None,
    commit: bool = True,
) -> LocutusAuditEntry:
    """Append an audit entry for a mutating Locutus action.

    Commits independently of the caller's transaction so the record persists
    even if the parent operation's own commit later fails.
    """
    entry = LocutusAuditEntry(
        run_id=run_id,
        actor=actor,
        action=action,
        target=target,
        payload_summary=payload_summary,
        result=result,
    )
    db.add(entry)
    if commit:
        await db.commit()
        await db.refresh(entry)
    return entry


async def list_audit_entries(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    actor: str | None = None,
    action: str | None = None,
) -> dict:
    """List audit entries newest-first, paginated and optionally filtered."""
    page = max(1, page)
    size = max(1, min(100, size))

    query = select(LocutusAuditEntry)

    if actor and actor.strip():
        query = query.where(LocutusAuditEntry.actor == actor.strip())

    if action and action.strip():
        query = query.where(LocutusAuditEntry.action == action.strip())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * size
    items_result = await db.execute(
        query.offset(offset).limit(size).order_by(LocutusAuditEntry.created_at.desc())
    )
    items = list(items_result.scalars().all())

    pages = math.ceil(total / size) if total > 0 else 0

    return {"items": items, "total": total, "page": page, "size": size, "pages": pages}


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
