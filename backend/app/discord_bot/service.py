"""
Locutus Service Layer.

Business Logic für alle Locutus-Funktionen:
- Chat (LLM-Integration)
- Suche (Notes + Vault)
- Status (Archon + Tasks)
- Notiz erstellen
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.second_brain.models import Note
from app.second_brain.service import create_note

from .config import BotConfig, LlmConfig
from .llm import LlmClient, LlmError
from .models import Command, Response

logger = logging.getLogger(__name__)

# System-Prompt für Locutus
LOCUTUS_SYSTEM_PROMPT = """
Du bist Locutus, ein knapper technischer Bot von BorgOS.
Antworte kurz und präzise. Keine Smalltalk. Keine Ausreden.
Wenn du etwas nicht weißt, sage "N/A" statt zu raten.
Formatiere Code in Backticks. Formatiere Dates als YYYY-MM-DD.
"""


class DiscordBotService:
    """
    Locutus Service.

    Bündelt alle Business-Logic für Discord-Bot-Funktionen.
    """

    def __init__(self, config: BotConfig) -> None:
        """Initialisiere Service mit Config."""
        self._config = config
        self._llm_client: Optional[LlmClient] = None

    async def start(self) -> None:
        """Starte Service (LLM-Client initialisieren)."""
        self._llm_client = LlmClient(self._config.llm)
        await self._llm_client.start()
        logger.info("DiscordBotService started")

    async def stop(self) -> None:
        """Stoppe Service (LLM-Client schließen)."""
        if self._llm_client:
            await self._llm_client.stop()
        logger.info("DiscordBotService stopped")

    async def chat(self, message: str, user_id: int) -> Response:
        """
        Verarbeite eine Chat-Nachricht.

        Sende Nachricht an LM Studio und gib Antwort zurück.
        """
        if not self._llm_client:
            return Response(
                content="Fehler: LLM-Service nicht verfügbar",
                is_error=True,
            )

        try:
            messages = [{"role": "user", "content": message}]
            answer = await self._llm_client.chat(messages, LOCUTUS_SYSTEM_PROMPT)
            return Response(content=answer)

        except LlmError as e:
            logger.error(f"LLM chat error: {e}")
            return Response(
                content=f"Fehler: LLM nicht erreichbar — {str(e)}",
                is_error=True,
            )

    async def search(self, query: str) -> Response:
        """
        Durchsuche Notes und Vault nach query.

        Returns:
            Response mit Suchergebnissen
        """
        try:
            async with AsyncSessionLocal() as db:
                # Suche in DB Notes (LIKE-Search auf title und content)
                notes_result = await db.execute(
                    select(Note).where(
                        Note.is_archived == False,
                        (Note.title.ilike(f"%{query}%")) | (Note.content.ilike(f"%{query}%")),
                    ).limit(10)
                )
                notes = notes_result.scalars().all()

                if not notes:
                    return Response(content=f"Keine Notes gefunden für: {query}")

                lines = [f"Notes ({len(notes)}):"]
                for note in notes[:5]:
                    lines.append(f"  • {note.title} (ID: {note.id})")

                return Response(content="\n".join(lines))

        except Exception as e:
            logger.error(f"Search error: {e}")
            return Response(
                content=f"Fehler: Suche fehlgeschlagen — {str(e)}",
                is_error=True,
            )

    async def status(self) -> Response:
        """
        Zeige Task- und Archon-Status.

        Returns:
            Response mit aktuellem Status
        """
        try:
            from app.archon_system.service import sync_and_get_health
            from app.task_automation.models import Task, TaskRun
            from app.task_automation.service import get_task

            async with AsyncSessionLocal() as db:
                # Aktuelle Tasks
                tasks_result = await db.execute(
                    select(Task).where(Task.is_enabled == True)
                )
                tasks = tasks_result.scalars().all()

                # Aktive TaskRuns
                runs_result = await db.execute(
                    select(TaskRun).where(TaskRun.status == "running").order_by(TaskRun.started_at.desc()).limit(5)
                )
                active_runs = runs_result.scalars().all()

                lines = ["Status:"]

                # Aktive Tasks
                lines.append(f"  Tasks aktiv: {len(tasks)}")

                # Aktive Runs
                if active_runs:
                    lines.append(f"  Runs aktiv: {len(active_runs)}")
                    for run in active_runs[:3]:
                        task = await get_task(db, run.task_id)
                        task_name = task.name if task else f"#{run.task_id}"
                        lines.append(f"    • {task_name} (#{run.id})")
                else:
                    lines.append("  Runs aktiv: 0")

                # Archon Health
                try:
                    archon_health = await sync_and_get_health(db)
                except Exception:
                    archon_health = {"online": False, "cached": True}

                archon_status = "online" if archon_health.get("online") else "offline"
                lines.append(f"  Archon: {archon_status}")

                return Response(content="\n".join(lines))

        except Exception as e:
            logger.error(f"Status error: {e}")
            return Response(
                content=f"Fehler: Status-Abfrage fehlgeschlagen — {str(e)}",
                is_error=True,
            )

    async def create_note(self, content: str) -> Response:
        """
        Erstelle eine Notiz aus content.

        Extrahiert Titel aus content (erste Zeile oder erster Satz).
        """
        try:
            # Extrahiere Titel: erste Zeile bis ':' oder erste 100 Zeichen
            title = content.split("\n")[0]
            if ":" in title:
                title = title.split(":")[0].strip()
            title = title[:100] or "Unbenannt"

            # Content ist der Rest nach dem Titel
            note_content = content
            if "\n" in content:
                note_content = "\n".join(content.split("\n")[1:])
            elif ":" in content and len(content.split(":")) > 1:
                note_content = content.split(":", 1)[1].strip()

            async with AsyncSessionLocal() as db:
                note = await create_note(db, title=title, content=note_content, tags=[])
                await db.commit()

                return Response(content=f"Notiz erstellt: {title} (ID: {note.id})")

        except Exception as e:
            logger.error(f"Create note error: {e}")
            return Response(
                content=f"Fehler: Notiz-Erstellung fehlgeschlagen — {str(e)}",
                is_error=True,
            )
