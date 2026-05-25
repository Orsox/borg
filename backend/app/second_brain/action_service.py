"""Service layer for Action Memory — CRUD, search, stats operations."""

import json
import math
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.second_brain.action_models import ActionMemory


def _tags_to_json(tags: list[str]) -> str:
    return json.dumps(tags)


def _json_to_tags(tags_str: str) -> list[str]:
    try:
        return json.loads(tags_str)
    except (json.JSONDecodeError, TypeError):
        return []


def _metadata_to_json(metadata: dict) -> str:
    return json.dumps(metadata)


def _json_to_metadata(metadata_str: str) -> dict:
    try:
        return json.loads(metadata_str)
    except (json.JSONDecodeError, TypeError):
        return {}


def _tools_to_json(tools: list[str]) -> str:
    return json.dumps(tools)


def _json_to_tools(tools_str: str) -> list[str]:
    try:
        return json.loads(tools_str)
    except (json.JSONDecodeError, TypeError):
        return []


async def create_action_memory(
    db: AsyncSession,
    title: str,
    description: str = "",
    action_type: str = "general",
    tools_used: list[str] | None = None,
    status: str = "success",
    duration_ms: int | None = None,
    output_path: str | None = None,
    metadata: dict | None = None,
    tags: list[str] | None = None,
    source_kind: str | None = None,
    source_ref: str | None = None,
) -> ActionMemory:
    """Create a new action memory entry."""
    if tools_used is None:
        tools_used = []
    if metadata is None:
        metadata = {}
    if tags is None:
        tags = []

    action = ActionMemory(
        title=title,
        description=description,
        action_type=action_type,
        tools_used=_tools_to_json(tools_used),
        status=status,
        is_archived=False,
        duration_ms=duration_ms,
        output_path=output_path,
        metadata_json=_metadata_to_json(metadata),
        tags=_tags_to_json(tags),
        source_kind=source_kind,
        source_ref=source_ref,
    )
    db.add(action)
    await db.commit()
    await db.refresh(action)
    return action


async def get_action_memory(db: AsyncSession, action_id: int) -> ActionMemory | None:
    """Get a single action memory by ID (including archived)."""
    result = await db.execute(
        select(ActionMemory).where(ActionMemory.id == action_id)
    )
    return result.scalar_one_or_none()


async def list_action_memories(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    search: str | None = None,
    action_type: str | None = None,
    status: str | None = None,
    archived: bool = False,
) -> dict:
    """
    List action memories with pagination and filtering.

    By default excludes archived entries. Set archived=True to show only archived.
    """
    page = max(1, page)
    size = max(1, min(100, size))

    query = select(ActionMemory)

    # Archive filter
    if archived:
        query = query.where(ActionMemory.is_archived == True)  # noqa: E712
    else:
        query = query.where(ActionMemory.is_archived == False)  # noqa: E712

    # Full-text search
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            ActionMemory.title.ilike(term)
            | ActionMemory.description.ilike(term)
            | ActionMemory.metadata_json.ilike(term)
            | ActionMemory.tools_used.ilike(term)
            | ActionMemory.tags.ilike(term)
        )

    # Action type filter
    if action_type and action_type.strip():
        query = query.where(ActionMemory.action_type == action_type.strip())

    # Status filter
    if status and status.strip():
        query = query.where(ActionMemory.status == status.strip())

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginated results
    offset = (page - 1) * size
    items_result = await db.execute(
        query.offset(offset).limit(size).order_by(ActionMemory.created_at.desc())
    )
    items = list(items_result.scalars().all())

    pages = math.ceil(total / size) if total > 0 else 0

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }


async def update_action_memory(
    db: AsyncSession,
    action_id: int,
    title: str | None = None,
    description: str | None = None,
    action_type: str | None = None,
    tools_used: list[str] | None = None,
    status: str | None = None,
    duration_ms: int | None = None,
    output_path: str | None = None,
    metadata: dict | None = None,
    tags: list[str] | None = None,
) -> ActionMemory | None:
    """Update an action memory entry."""
    action = await get_action_memory(db, action_id)
    if not action:
        return None

    if title is not None:
        action.title = title
    if description is not None:
        action.description = description
    if action_type is not None:
        action.action_type = action_type
    if tools_used is not None:
        action.tools_used = _tools_to_json(tools_used)
    if status is not None:
        action.status = status
    if duration_ms is not None:
        action.duration_ms = duration_ms
    if output_path is not None:
        action.output_path = output_path
    if metadata is not None:
        action.metadata_json = _metadata_to_json(metadata)
    if tags is not None:
        action.tags = _tags_to_json(tags)

    action.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(action)
    return action


async def archive_action_memory(db: AsyncSession, action_id: int) -> ActionMemory | None:
    """Soft-delete an action memory (set is_archived=True)."""
    action = await get_action_memory(db, action_id)
    if not action:
        return None

    action.is_archived = True
    action.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(action)
    return action


async def get_action_memory_stats(db: AsyncSession) -> dict:
    """
    Get statistics about action memories.
    Excludes archived entries.
    """
    active_query = select(ActionMemory).where(ActionMemory.is_archived == False)  # noqa: E712

    # Total count
    total = (await db.execute(
        select(func.count()).select_from(active_query.subquery())
    )).scalar() or 0

    # Status counts
    success_count = (await db.execute(
        select(func.count()).select_from(
            active_query.where(ActionMemory.status == "success").subquery()
        )
    )).scalar() or 0

    failed_count = (await db.execute(
        select(func.count()).select_from(
            active_query.where(ActionMemory.status == "failed").subquery()
        )
    )).scalar() or 0

    in_progress_count = (await db.execute(
        select(func.count()).select_from(
            active_query.where(ActionMemory.status == "in_progress").subquery()
        )
    )).scalar() or 0

    # Action type distribution
    type_result = await db.execute(
        select(
            ActionMemory.action_type,
            func.count(ActionMemory.id).label("count"),
        )
        .where(ActionMemory.is_archived == False)  # noqa: E712
        .group_by(ActionMemory.action_type)
        .order_by(func.count(ActionMemory.id).desc())
    )
    action_types = [
        {"type": row.action_type, "count": row.count}
        for row in type_result.all()
    ]

    return {
        "total": total,
        "success_count": success_count,
        "failed_count": failed_count,
        "in_progress_count": in_progress_count,
        "action_types": action_types,
    }


async def seed_default_actions(db: AsyncSession) -> None:
    """Seed initial action memory entries if the table is empty."""
    from sqlalchemy import select

    result = await db.execute(select(func.count()).select_from(ActionMemory))
    count = result.scalar() or 0
    if count > 0:
        return

    await create_action_memory(
        db,
        title="IR Sensor PowerPoint Presentation",
        description="Created a professional PowerPoint presentation about the IR Sensor project using python-pptx in a virtual environment. The presentation covers project overview, architecture, technical details, and next steps.",
        action_type="presentation_creation",
        tools_used=["python-pptx", "venv", "bash"],
        status="success",
        duration_ms=45000,
        output_path="IR-Sensor_Praesentation.pptx",
        metadata={"slide_count": 13, "venv": True, "template": "custom"},
        tags=["presentation", "ir-sensor", "python-pptx"],
    )
