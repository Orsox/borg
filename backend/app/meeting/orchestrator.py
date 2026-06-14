"""
Conference-room orchestrator.

Runs a meeting as a background task: the personas take turns round-robin for a
chosen number of rounds, each seeing the full shared transcript before it
speaks. Turns are appended to an in-memory session as they complete; the
frontend polls the session for new turns and the current speaker. No DB —
meetings are ephemeral (same philosophy as the in-memory chat histories in
``discord_bot/service.py``).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.database import AsyncSessionLocal
from app.discord_bot.config import BotConfig
from app.discord_bot.llm import LlmClient, LlmError
from app.discord_bot.service import _strip_directive_markers
from app.shared import tracing

from .personas import MeetingPersona, build_personas_from_db

logger = logging.getLogger(__name__)

# Speaker key for Orsox's own seeded theme / follow-up turns in the transcript.
SPEAKER_ORSOX = "orsox"

# Round budget bounds — a meeting of 1..12 rounds. The default is used when the
# frontend sends a follow-up without the /meeting codeword.
DEFAULT_ROUNDS = 3
MAX_ROUNDS = 12

# Status values a session moves through.
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_ERROR = "error"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MeetingTurn:
    """One utterance in the shared transcript."""

    speaker: str  # persona key, or SPEAKER_ORSOX
    display_name: str
    content: str
    ts: str = field(default_factory=_now)


@dataclass
class MeetingSession:
    """In-memory state of one conference room."""

    id: str
    theme: str
    rounds_total: int
    transcript: list[MeetingTurn] = field(default_factory=list)
    rounds_done: int = 0
    status: str = STATUS_RUNNING
    speaking: Optional[str] = None  # persona key whose turn is in flight
    error: Optional[str] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


def _build_meeting_suffix(persona: MeetingPersona, others: list[str]) -> str:
    """Append the roundtable framing to a persona's base system prompt.

    Analogous to the ``from_peer`` suffix in DiscordBotService: it tells the
    persona this is a moderated roundtable, who else is present, and that
    directive markers are forbidden here (no memory/agent/repo side effects
    from inside a meeting).
    """
    participants = ", ".join(others) if others else "keine weiteren"
    return (
        "\n\nDu nimmst gerade an einer Konferenz im BorgOS-Besprechungsraum teil. "
        f"Orsox moderiert die Sitzung; weitere Teilnehmer am Tisch: {participants}. "
        "Es ist eine Gesprächsrunde — sprich in deiner Stimme, beziehe dich auf das "
        "bisher Gesagte, sprich die anderen bei Bedarf mit Namen an und bringe die "
        "Diskussion voran. Halte deinen Beitrag knapp und prägnant (wenige Sätze) — "
        "es kommen weitere Runden. Wiederhole nicht, was bereits gesagt wurde. "
        "Antworte in der Sprache des Themas. Beginne deine Antwort NIEMALS mit "
        "\"[MEMORY:\", \"[AGENT:\" oder \"[GITLAB_REPO:\" — solche Aufträge gibt es "
        "in einer Sitzung nicht."
    )


def _render_transcript(session: MeetingSession, persona: MeetingPersona) -> str:
    """Render the shared transcript into the single user message for a turn."""
    lines = [f"Thema der Sitzung: {session.theme}", ""]
    if session.transcript:
        lines.append("Bisheriger Verlauf:")
        for turn in session.transcript:
            lines.append(f"{turn.display_name}: {turn.content}")
        lines.append("")
    lines.append(
        f"Du bist {persona.display_name}. Du bist an der Reihe. "
        f"Antworte als {persona.display_name}."
    )
    return "\n".join(lines)


class MeetingService:
    """Singleton service that owns the LLM clients and the session registry."""

    def __init__(self) -> None:
        self._personas: list[MeetingPersona] = []
        self._clients: dict[str, LlmClient] = {}
        self._sessions: dict[str, MeetingSession] = {}

    async def start(self) -> None:
        """Load personas from DB and spin up one LlmClient per persona."""
        async with AsyncSessionLocal() as db:
            self._personas = await build_personas_from_db(db)
        for persona in self._personas:
            client = LlmClient(persona.llm_config)
            await client.start()
            self._clients[persona.key] = client
        logger.info("MeetingService started with personas: %s", [p.key for p in self._personas])

    async def stop(self) -> None:
        """Close all LlmClients."""
        for client in self._clients.values():
            await client.stop()
        self._clients.clear()
        logger.info("MeetingService stopped")

    @property
    def personas(self) -> list[MeetingPersona]:
        return self._personas

    def get_session(self, session_id: str) -> Optional[MeetingSession]:
        return self._sessions.get(session_id)

    def start_meeting(self, theme: str, rounds: int) -> MeetingSession:
        """Create a session and launch the background meeting task."""
        rounds = max(1, min(MAX_ROUNDS, rounds))
        session = MeetingSession(
            id=f"meeting-{uuid.uuid4().hex[:8]}",
            theme=theme.strip(),
            rounds_total=rounds,
            transcript=[MeetingTurn(speaker=SPEAKER_ORSOX, display_name="Orsox", content=theme.strip())],
        )
        self._sessions[session.id] = session
        asyncio.create_task(self._run_meeting(session, rounds), name=session.id)
        return session

    def add_message(self, session_id: str, message: str, rounds: int) -> Optional[MeetingSession]:
        """Inject an Orsox follow-up and run another round budget on the same room.

        Returns None if the session is unknown; raises ValueError if a meeting
        is still running (the frontend should wait for status done/error).
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.status == STATUS_RUNNING:
            raise ValueError("meeting still in progress")

        rounds = max(1, min(MAX_ROUNDS, rounds))
        session.transcript.append(
            MeetingTurn(speaker=SPEAKER_ORSOX, display_name="Orsox", content=message.strip())
        )
        session.status = STATUS_RUNNING
        session.error = None
        session.rounds_total += rounds
        asyncio.create_task(self._run_meeting(session, rounds), name=session.id)
        return session

    async def _run_meeting(self, session: MeetingSession, rounds: int) -> None:
        """Drive ``rounds`` round-robin rounds, appending each turn as it lands."""
        async with session.lock:
            try:
                for _ in range(rounds):
                    for persona in self._personas:
                        session.speaking = persona.key
                        content = await self._take_turn(session, persona)
                        session.transcript.append(
                            MeetingTurn(
                                speaker=persona.key,
                                display_name=persona.display_name,
                                content=content,
                            )
                        )
                        session.speaking = None
                    session.rounds_done += 1
                session.status = STATUS_DONE
            except LlmError as e:
                logger.error("Meeting %s LLM error: %s", session.id, e)
                session.status = STATUS_ERROR
                session.error = str(e)
            except Exception as e:  # noqa: BLE001 — surface any failure to the UI
                logger.exception("Meeting %s failed", session.id)
                session.status = STATUS_ERROR
                session.error = str(e)
            finally:
                session.speaking = None

    async def _take_turn(self, session: MeetingSession, persona: MeetingPersona) -> str:
        """Build the prompt for one persona's turn and call its LLM."""
        others = [p.display_name for p in self._personas if p.key != persona.key]
        system_prompt = persona.system_prompt
        async with AsyncSessionLocal() as db:
            recalled = await persona.recall(db)
        if recalled:
            system_prompt += (
                "\n\nDinge, die du dir bereits gemerkt hast (nutze sie, wenn relevant):\n"
                + "\n".join(recalled)
            )
        system_prompt += _build_meeting_suffix(persona, others)

        client = self._clients[persona.key]
        user_message = _render_transcript(session, persona)
        with tracing.trace_span(
            "meeting-turn",
            persona=persona.key,
            session_id=session.id,
            tags=["meeting"],
            input=session.theme,
        ) as span:
            answer = await client.chat([{"role": "user", "content": user_message}], system_prompt)
            span.update(output=answer)
        return _strip_directive_markers(answer)
