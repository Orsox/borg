"""
Participant registry for the conference room.

Personas are loaded dynamically from the personas DB table. Only active personas
with ``include_in_meetings=True`` appear at the round-robin table.

Reuses the canonical LLM wiring from the Discord bot so the characters sound
identical across surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.discord_bot.config import LlmConfig
from app.locutus import service as locutus_service
from app.seven_of_nine import service as seven_service

# How many of a persona's own memories to fold into its system prompt.
_MEMORY_RECALL_LIMIT = 8

# Fallback colour when a persona row has no color set.
_DEFAULT_COLOR = "#00e5ff"

# Known persona recall functions — extended when new personas add memory stores.
_RECALL_FUNCTIONS: dict[str, Callable[[AsyncSession], Awaitable[list[str]]]] = {}


def _register_recall(key: str, fn: Callable[[AsyncSession], Awaitable[list[str]]]) -> None:
    """Register a memory-recall function for a persona key."""
    _RECALL_FUNCTIONS[key] = fn


async def _recall_locutus(db: AsyncSession) -> list[str]:
    memories = await locutus_service.list_character_memories(db, size=_MEMORY_RECALL_LIMIT)
    return [f"- {m.title}: {m.content}" for m in memories["items"] if m.content]


async def _recall_seven(db: AsyncSession) -> list[str]:
    memories = await seven_service.list_memories(db, size=_MEMORY_RECALL_LIMIT)
    return [f"- {m.title}: {m.content}" for m in memories["items"] if m.content]


# Register known recall functions at module load time.
_register_recall("locutus", _recall_locutus)
_register_recall("seven", _recall_seven)


@dataclass(frozen=True)
class MeetingPersona:
    """A participant at the table."""

    key: str
    display_name: str
    system_prompt: str
    color: str
    llm_config: LlmConfig
    recall: Callable[[AsyncSession], Awaitable[list[str]]]


async def _build_llm_for_persona(db: AsyncSession, persona) -> Optional[LlmConfig]:
    """Build an LlmConfig from a Persona DB row."""
    from app.personas.service import build_llm_config as svc_build
    return await svc_build(db, persona.key)


async def build_personas_from_db(db: AsyncSession) -> list[MeetingPersona]:
    """
    Construct the ordered participant list from DB personas.

    Only active personas with include_in_meetings=True are included.
    Ordered by persona key for deterministic round-robin sequencing.
    """
    from app.personas.service import list_active_personas

    db_personas = await list_active_personas(db, include_meeting_only=True)

    participants: list[MeetingPersona] = []
    for p in db_personas:
        llm_config = await _build_llm_for_persona(db, p)
        if llm_config is None:
            continue  # Skip personas without valid LLM config

        recall_fn = _RECALL_FUNCTIONS.get(p.key)
        system_prompt = (p.system_prompt or "").strip()
        if not system_prompt:
            continue  # Skip personas without a system prompt

        participants.append(MeetingPersona(
            key=p.key,
            display_name=p.display_name,
            system_prompt=system_prompt,
            color=(p.color or _DEFAULT_COLOR),
            llm_config=llm_config,
            # No registered recall function — use empty default
            recall=recall_fn or (lambda _: []),
        ))

    return participants
