"""Service layer for the Seven of Nine module — persona, memory, and audit operations."""

import math
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.seven_of_nine.models import DroneAuditEntry, DroneMemoryEntry, DroneProfile

DEFAULT_PROFILE_CONTENT = (
    "# Seven of Nine\n\n"
    "Wissenschafts- und Engineering-Drohne von BorgOS. Analysiert Code, Architektur "
    "und technische Probleme mit Effizienz und Präzision.\n"
)


async def get_or_create_profile(db: AsyncSession) -> DroneProfile:
    """Get the drone profile, creating a default if none exists."""
    result = await db.execute(select(DroneProfile).limit(1))
    profile = result.scalar_one_or_none()
    if profile:
        return profile

    profile = DroneProfile(content=DEFAULT_PROFILE_CONTENT)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def update_profile(db: AsyncSession, content: str) -> DroneProfile:
    """Update the drone profile content."""
    profile = await get_or_create_profile(db)
    profile.content = content
    profile.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(profile)
    return profile


async def create_memory(
    db: AsyncSession,
    title: str,
    content: str = "",
    category: str = "general",
) -> DroneMemoryEntry:
    """Create a new drone memory entry."""
    entry = DroneMemoryEntry(title=title, content=content, category=category)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    await record_action(
        db,
        action="drone_memory_create",
        target=str(entry.id),
        payload_summary=entry.title,
    )
    return entry


async def list_memories(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    search: str | None = None,
    category: str | None = None,
    archived: bool = False,
) -> dict:
    """List drone memories with pagination and filtering."""
    page = max(1, page)
    size = max(1, min(100, size))

    query = select(DroneMemoryEntry)

    if archived:
        query = query.where(DroneMemoryEntry.is_archived == True)  # noqa: E712
    else:
        query = query.where(DroneMemoryEntry.is_archived == False)  # noqa: E712

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            DroneMemoryEntry.title.ilike(term)
            | DroneMemoryEntry.content.ilike(term)
        )

    if category and category.strip():
        query = query.where(DroneMemoryEntry.category == category.strip())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * size
    items_result = await db.execute(
        query.offset(offset).limit(size).order_by(DroneMemoryEntry.created_at.desc())
    )
    items = list(items_result.scalars().all())

    pages = math.ceil(total / size) if total > 0 else 0

    return {"items": items, "total": total, "page": page, "size": size, "pages": pages}


async def archive_memory(db: AsyncSession, entry_id: int) -> DroneMemoryEntry | None:
    """Soft-delete a drone memory entry."""
    result = await db.execute(select(DroneMemoryEntry).where(DroneMemoryEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        return None

    entry.is_archived = True
    entry.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(entry)
    await record_action(
        db,
        action="drone_memory_archive",
        target=str(entry.id),
        payload_summary=entry.title,
    )
    return entry


async def record_action(
    db: AsyncSession,
    *,
    action: str,
    actor: str = "seven_of_nine",
    target: str | None = None,
    payload_summary: str | None = None,
    result: str = "ok",
    run_id: str | None = None,
    commit: bool = True,
) -> DroneAuditEntry:
    """Append an audit entry for a mutating Seven of Nine action.

    Commits independently of the caller's transaction so the record persists
    even if the parent operation's own commit later fails.
    """
    entry = DroneAuditEntry(
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

    query = select(DroneAuditEntry)

    if actor and actor.strip():
        query = query.where(DroneAuditEntry.actor == actor.strip())

    if action and action.strip():
        query = query.where(DroneAuditEntry.action == action.strip())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * size
    items_result = await db.execute(
        query.offset(offset).limit(size).order_by(DroneAuditEntry.created_at.desc())
    )
    items = list(items_result.scalars().all())

    pages = math.ceil(total / size) if total > 0 else 0

    return {"items": items, "total": total, "page": page, "size": size, "pages": pages}


async def seed_default_data(db: AsyncSession) -> None:
    """Seed initial Seven of Nine data if tables are empty."""
    result = await db.execute(select(func.count()).select_from(DroneProfile))
    profile_count = result.scalar() or 0
    if profile_count == 0:
        await get_or_create_profile(db)
