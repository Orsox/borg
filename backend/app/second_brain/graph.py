"""Wiki-link parser and knowledge graph operations for the Second Brain."""

import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.second_brain.models import Note, NoteLink


# Pattern to match [[Note Title]] wiki-links
WIKI_LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")


def parse_wiki_links(content: str) -> list[str]:
    """Extract wiki-link titles from note content."""
    return WIKI_LINK_PATTERN.findall(content)


async def resolve_wiki_links(
    db: AsyncSession,
    note_id: int,
    content: str,
) -> None:
    """
    Resolve wiki-links in note content and sync note_links table.
    
    For each [[Title]] in content:
    - If a note with that title exists, create/update the link
    - If no note exists, silently skip (no dangling edges)
    
    Removes links that no longer exist in the content.
    """
    # Parse current wiki-links from content
    new_link_titles = parse_wiki_links(content)
    
    # Get existing outgoing links for this note
    result = await db.execute(
        select(NoteLink).where(NoteLink.source_id == note_id)
    )
    existing_links = list(result.scalars().all())
    
    # Build set of currently linked target note IDs
    existing_target_ids = {link.target_id for link in existing_links}
    
    # Resolve each wiki-link title to a note
    resolved_target_ids = set()
    for title in new_link_titles:
        # Find note by title (case-insensitive)
        result = await db.execute(
            select(Note).where(Note.title.ilike(title))
        )
        target_note = result.scalar_one_or_none()
        
        if target_note and target_note.id != note_id:  # No self-links
            resolved_target_ids.add(target_note.id)
    
    # Remove links that no longer exist in content
    for link in existing_links:
        if link.target_id not in resolved_target_ids:
            await db.delete(link)
    
    # Add new links
    for target_id in resolved_target_ids:
        if target_id not in existing_target_ids:
            new_link = NoteLink(source_id=note_id, target_id=target_id)
            db.add(new_link)
