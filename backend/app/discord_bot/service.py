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
Du bist Locutus, ein technischer Assistent von BorgOS.
Du antwortest natürlich und hilfst bei Fragen zu Archon, Tasks, Notes und Vault.
Sei freundlich, aber knapp. Keine langen Ausreden.
Wenn du etwas nicht weißt, sag ehrlich dass du es nicht weißt.
Formatiere Code in Backticks. Formatiere Dates als YYYY-MM-DD.
Sprich Deutsch, wenn der User Deutsch schreibt.
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
        Durchsuche Notes (DB) und Vault (Dateisystem) nach query.

        Returns:
            Response mit kombinierten Suchergebnissen
        """
        try:
            results_parts: list[str] = []

            # --- 1. DB Notes Suche ---
            try:
                async with AsyncSessionLocal() as db:
                    notes_result = await db.execute(
                        select(Note).where(
                            Note.is_archived == False,
                            (
                                Note.title.ilike(f"%{query}%")
                                | Note.content.ilike(f"%{query}%")
                            ),
                        ).limit(10)
                    )
                    notes = notes_result.scalars().all()

                    if notes:
                        lines = [f"📝 Notes ({len(notes)}):"]
                        for note in notes[:5]:
                            # Extrahiere Snippet aus dem Content
                            snippet = self._extract_snippet(note.content, query)
                            lines.append(f"  • {note.title} (ID: {note.id})")
                            if snippet:
                                lines.append(f"    …{snippet}…")
                        results_parts.append("\n".join(lines))
            except Exception as db_err:
                logger.warning(f"DB search failed: {db_err}")

            # --- 2. Vault Suche ---
            try:
                vault_results = self._search_vault(query)
                if vault_results:
                    lines = [f"📂 Vault ({len(vault_results)}):"]
                    for vr in vault_results[:5]:
                        lines.append(f"  • {vr['path']}")
                        if vr.get("snippet"):
                            lines.append(f"    …{vr['snippet']}…")
                    results_parts.append("\n".join(lines))
            except Exception as vault_err:
                logger.warning(f"Vault search failed: {vault_err}")

            if not results_parts:
                return Response(content=f"Keine Ergebnisse für: {query}")

            return Response(content="\n\n".join(results_parts))

        except Exception as e:
            logger.error(f"Search error: {e}")
            return Response(
                content=f"Fehler: Suche fehlgeschlagen — {str(e)}",
                is_error=True,
            )

    def _extract_snippet(self, content: str, query: str, max_len: int = 120) -> str:
        """
        Extrahiere ein Snippet aus dem Content um den Query-Treffer herum.

        Args:
            content: Der vollständige Content einer Note
            query: Der Suchbegriff
            max_len: Maximale Snippet-Länge

        Returns:
            Snippet-String oder leer wenn kein Treffer
        """
        if not content or not query:
            return ""

        query_lower = query.lower()
        content_lower = content.lower()
        idx = content_lower.find(query_lower)

        if idx == -1:
            # Fallback: erster Absatz
            first_line = content.split("\n")[0].strip()
            return first_line[:max_len] if first_line else ""

        # Extrahiere Text um den Treffer herum
        start = max(0, idx - 40)
        end = min(len(content), idx + len(query) + 40)
        snippet = content[start:end].strip()

        # Kürze bei Bedarf
        if len(snippet) > max_len:
            snippet = snippet[:max_len] + "…"

        return snippet

    def _search_vault(self, query: str, vault_path: Optional[str] = None) -> list[dict]:
        """
        Durchsuche das Obsidian-Vault (Dateisystem) nach query.

        Args:
            query: Der Suchbegriff
            vault_path: Optionaler Vault-Pfad, sonst ~/.

        Returns:
            Liste von dicts mit 'path' und 'snippet'
        """
        import os
        from pathlib import Path

        if vault_path is None:
            vault_path = os.path.expanduser("~/Memory")

        vault = Path(vault_path)
        if not vault.exists() or not vault.is_dir():
            return []

        query_lower = query.lower()
        results: list[dict] = []

        for md_file in vault.rglob("*.md"):
            # Skip excluded directories
            parts = list(md_file.parts)
            excluded = {".git", "__pycache__", "node_modules", ".venv", ".obsidian", ".trash", "expired"}
            if any(part in excluded for part in parts):
                continue

            try:
                text = md_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            if query_lower not in text.lower():
                continue

            rel_path = str(md_file.relative_to(vault))
            snippet = self._extract_snippet(text, query, max_len=100)

            results.append({
                "path": rel_path,
                "snippet": snippet,
            })

        return results

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
