"""
Participant registry for the conference room.

One entry per persona that can sit at the table. Seeded with the two personas
that exist today (Locutus, Seven of Nine); adding a third later means adding a
single ``MeetingPersona`` here — the orchestrator iterates the list in order,
which *is* the round-robin speaking order.

Reuses the canonical system prompts and LLM wiring from the Discord bot so the
characters sound identical across surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.discord_bot.config import BotConfig, LlmConfig
from app.discord_bot.service import (
    LOCUTUS_SYSTEM_PROMPT,
    PERSONA_LOCUTUS,
    PERSONA_SEVEN,
    SEVEN_SYSTEM_PROMPT,
)
from app.locutus import service as locutus_service
from app.seven_of_nine import service as seven_service

# How many of a persona's own memories to fold into its system prompt — same
# recall discipline as DiscordBotService._MEMORY_RECALL_LIMIT.
_MEMORY_RECALL_LIMIT = 8

# Distinct accent colour per persona, handed to the frontend so each station
# and transcript label gets its own hue (Borg cyan family).
_LOCUTUS_COLOR = "#00e5ff"
_SEVEN_COLOR = "#7cf67c"


async def _recall_locutus(db: AsyncSession) -> list[str]:
    memories = await locutus_service.list_character_memories(db, size=_MEMORY_RECALL_LIMIT)
    return [f"- {m.title}: {m.content}" for m in memories["items"] if m.content]


async def _recall_seven(db: AsyncSession) -> list[str]:
    memories = await seven_service.list_memories(db, size=_MEMORY_RECALL_LIMIT)
    return [f"- {m.title}: {m.content}" for m in memories["items"] if m.content]


@dataclass(frozen=True)
class MeetingPersona:
    """A participant at the table."""

    key: str
    display_name: str
    system_prompt: str
    color: str
    # Builds the LlmConfig for this persona from the central BotConfig (base_url
    # + model_id live in BorgOS settings, one pair per persona).
    llm_config: LlmConfig
    # Returns this persona's recalled-memory lines (already formatted) for the
    # current DB session — folded into the system prompt at turn time.
    recall: Callable[[AsyncSession], Awaitable[list[str]]]


def build_personas(config: BotConfig) -> list[MeetingPersona]:
    """Construct the ordered participant list (= round-robin order)."""
    return [
        MeetingPersona(
            key=PERSONA_LOCUTUS,
            display_name="Locutus",
            system_prompt=LOCUTUS_SYSTEM_PROMPT,
            color=_LOCUTUS_COLOR,
            llm_config=config.llm,
            recall=_recall_locutus,
        ),
        MeetingPersona(
            key=PERSONA_SEVEN,
            display_name="Seven of Nine",
            system_prompt=SEVEN_SYSTEM_PROMPT,
            color=_SEVEN_COLOR,
            llm_config=config.seven_llm,
            recall=_recall_seven,
        ),
    ]
