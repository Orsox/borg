"""Service layer for Second Brain — note CRUD, search, graph operations."""

import json
import math
from datetime import datetime, timezone

from sqlalchemy import func, select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.second_brain.models import Note, NoteLink
from app.second_brain.graph import resolve_wiki_links


def _tags_to_json(tags: list[str]) -> str:
    return json.dumps(tags)


def _json_to_tags(tags_str: str) -> list[str]:
    try:
        return json.loads(tags_str)
    except (json.JSONDecodeError, TypeError):
        return []


async def create_note(
    db: AsyncSession,
    title: str,
    content: str = "",
    tags: list[str] | None = None,
) -> Note:
    """Create a new note and resolve wiki-links."""
    if tags is None:
        tags = []
    
    note = Note(
        title=title,
        content=content,
        tags=_tags_to_json(tags),
        is_archived=False,
    )
    db.add(note)
    await db.flush()  # Get the note ID
    
    # Resolve wiki-links
    await resolve_wiki_links(db, note.id, content)
    
    await db.commit()
    await db.refresh(note)
    return note


async def get_note(db: AsyncSession, note_id: int) -> Note | None:
    """Get a single note by ID (including archived)."""
    result = await db.execute(select(Note).where(Note.id == note_id))
    return result.scalar_one_or_none()


async def list_notes(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    search: str | None = None,
    tags: str | None = None,
    archived: bool = False,
) -> dict:
    """
    List notes with pagination and filtering.
    
    By default excludes archived notes. Set archived=True to show only archived.
    """
    page = max(1, page)
    size = max(1, min(100, size))
    
    query = select(Note)
    
    # Archive filter
    if archived:
        query = query.where(Note.is_archived == True)  # noqa: E712
    else:
        query = query.where(Note.is_archived == False)  # noqa: E712
    
    # Full-text search
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Note.title.ilike(term),
                Note.content.ilike(term),
            )
        )
    
    # Tag filter
    if tags and tags.strip():
        for tag in tags.split(","):
            tag = tag.strip()
            if tag:
                query = query.where(Note.tags.contains(f'"{tag}"'))
    
    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0
    
    # Paginated results
    offset = (page - 1) * size
    items_result = await db.execute(
        query.offset(offset).limit(size).order_by(Note.updated_at.desc())
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


async def update_note(
    db: AsyncSession,
    note_id: int,
    title: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
) -> Note | None:
    """Update a note and re-resolve wiki-links."""
    note = await get_note(db, note_id)
    if not note:
        return None
    
    if title is not None:
        note.title = title
    if content is not None:
        note.content = content
    if tags is not None:
        note.tags = _tags_to_json(tags)
    
    note.updated_at = datetime.now(timezone.utc)
    
    # Re-resolve wiki-links with current content
    await resolve_wiki_links(db, note.id, note.content)
    
    await db.commit()
    await db.refresh(note)
    return note


async def archive_note(db: AsyncSession, note_id: int) -> Note | None:
    """Soft-delete a note (set is_archived=True)."""
    note = await get_note(db, note_id)
    if not note:
        return None
    
    note.is_archived = True
    note.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(note)
    return note


async def get_backlinks(db: AsyncSession, note_id: int) -> list[Note]:
    """Get all notes that link to the given note."""
    note = await get_note(db, note_id)
    if not note:
        return []
    
    result = await db.execute(
        select(Note)
        .join(NoteLink, NoteLink.target_id == note_id)
        .where(Note.id == NoteLink.source_id)
        .where(Note.is_archived == False)  # noqa: E712
    )
    return list(result.scalars().all())


async def get_knowledge_graph(db: AsyncSession) -> dict:
    """
    Get the full knowledge graph as nodes and edges.
    Excludes archived notes.
    """
    # Get all non-archived notes
    notes_result = await db.execute(
        select(Note).where(Note.is_archived == False)  # noqa: E712
    )
    notes = list(notes_result.scalars().all())
    
    # Get all links between non-archived notes
    links_result = await db.execute(
        select(NoteLink)
        .join(Note, Note.id == NoteLink.source_id)
        .where(Note.is_archived == False)  # noqa: E712
    )
    links = list(links_result.scalars().all())
    
    nodes = [
        {
            "id": note.id,
            "title": note.title,
            "tags": _json_to_tags(note.tags),
        }
        for note in notes
    ]
    
    edges = [
        {"source": link.source_id, "target": link.target_id}
        for link in links
    ]
    
    return {"nodes": nodes, "edges": edges}
