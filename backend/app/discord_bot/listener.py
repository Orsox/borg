"""
Locutus SSE-Queue Listener.

Hört auf die sse_queue im Task-Automation-Modul und push-t
Notifications an Discord wenn Tasks starten/fertig/fehl schlagen.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.task_automation.scheduler import sse_queue

from .models import TaskEvent, TaskEventType, TaskNotification

logger = logging.getLogger(__name__)

# Dreaming events aren't Task-shaped (no task_id/task_name), so they're handled
# via a dedicated formatter rather than forced through TaskEvent/TaskNotification.
DREAMING_EVENT_TYPES = ("dreaming_run_started", "dreaming_run_completed")

# Gap-analysis runs as the final step of a dreaming cycle and surfaces draft
# ReasoningLog proposals — also not Task-shaped, gets its own formatter.
GAP_ANALYSIS_EVENT_TYPES = ("gap_analysis_completed",)

# Stage 4: an approved ReasoningLog drafts a skill file + SkillRecord (creation,
# not execution) — also not Task-shaped, gets its own formatter.
SKILL_CREATION_EVENT_TYPES = ("skill_drafted", "skill_draft_failed")


def _format_dreaming_event(event_dict: dict) -> Optional[str]:
    """Format a dreaming_run_* SSE event dict into a Discord notification string."""
    run_id = event_dict.get("run_id")
    if event_dict.get("type") == "dreaming_run_started":
        return f"🌙 Dreaming-Zyklus #{run_id} gestartet."

    status = event_dict.get("status")
    if status == "failed":
        err = event_dict.get("error")
        return (
            f"✗ Dreaming-Zyklus #{run_id} fehlgeschlagen — {err}."
            if err
            else f"✗ Dreaming-Zyklus #{run_id} fehlgeschlagen."
        )
    if "notes_created" in event_dict:
        n = event_dict["notes_created"]
        return f"✓ Dreaming-Zyklus #{run_id} abgeschlossen — {n} Notiz(en) erstellt."
    reason = event_dict.get("reason")
    return (
        f"ℹ Dreaming-Zyklus #{run_id} übersprungen — {reason}."
        if reason
        else f"ℹ Dreaming-Zyklus #{run_id} abgeschlossen."
    )


def _format_gap_analysis_event(event_dict: dict) -> Optional[str]:
    """Format a gap_analysis_completed SSE event into a Discord notification string.

    Lists newly drafted ReasoningLog proposals (status stays "draft" — these are
    proposals for human review, not actions taken).
    """
    proposals = event_dict.get("proposals") or []
    if not proposals:
        return None

    lines = [f"🧭 {len(proposals)} neue Verbesserungsvorschläge zur Prüfung (Entwurf):"]
    for p in proposals:
        lines.append(f"  • #{p.get('id')} {p.get('title')} — {p.get('trigger_description')}")
    lines.append("Prüfen & entscheiden über die BorgOS-UI (Locutus → Reasoning Logs).")
    return "\n".join(lines)


def _format_skill_creation_event(event_dict: dict) -> Optional[str]:
    """Format a skill_drafted/skill_draft_failed SSE event into a Discord notification string.

    The skill remains `status="draft"` either way — this only announces that the
    file + SkillRecord were generated (or why generation failed), never that the
    skill is ready to run.
    """
    if event_dict.get("type") == "skill_draft_failed":
        log_id = event_dict.get("reasoning_log_id")
        error = event_dict.get("error")
        return f"✗ Skill-Erstellung aus Vorschlag #{log_id} fehlgeschlagen — {error}."

    name = event_dict.get("skill_name")
    log_id = event_dict.get("reasoning_log_id")
    path = event_dict.get("file_path")
    return (
        f"🛠 Skill `{name}` aus Vorschlag #{log_id} entworfen, bereit zur Prüfung unter `{path}`."
    )


class TaskEventListener:
    """
    Listener für SSE-Task-Events.

    Liest Events aus der globalen sse_queue und formatiert
    sie als Discord-Notifications.
    """

    def __init__(self, notification_callback: callable) -> None:
        """
        Initialisiere TaskEventListener.

        Args:
            notification_callback: Async-Funktion die aufgerufen wird
                                   wenn eine Notification gesendet werden soll.
                                   Signatur: async (content: str) -> None
        """
        self._callback = notification_callback
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Starte den Listener."""
        if self._running:
            logger.warning("TaskEventListener already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._listen_loop())
        logger.info("TaskEventListener started")

    async def stop(self) -> None:
        """Stoppe den Listener."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TaskEventListener stopped")

    async def _listen_loop(self) -> None:
        """Hauptschleife: Liest Events aus sse_queue."""
        while self._running:
            try:
                event_dict = await asyncio.wait_for(sse_queue.get(), timeout=1.0)
                await self._process_event(event_dict)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in TaskEventListener: {e}")

    async def _process_event(self, event_dict: dict) -> None:
        """
        Verarbeite ein SSE-Event.

        Parst Event-Dict in TaskEvent, formatiert Notification,
        ruft notification_callback auf.
        """
        try:
            event_type = event_dict.get("type", "")

            if event_type in DREAMING_EVENT_TYPES:
                formatted = _format_dreaming_event(event_dict)
                if formatted:
                    logger.info(f"Dreaming notification: {formatted}")
                    await self._callback(formatted)
                return

            if event_type in GAP_ANALYSIS_EVENT_TYPES:
                formatted = _format_gap_analysis_event(event_dict)
                if formatted:
                    logger.info(f"Gap analysis notification: {formatted}")
                    await self._callback(formatted)
                return

            if event_type in SKILL_CREATION_EVENT_TYPES:
                formatted = _format_skill_creation_event(event_dict)
                if formatted:
                    logger.info(f"Skill creation notification: {formatted}")
                    await self._callback(formatted)
                return

            if event_type not in (
                TaskEventType.TASK_STARTED.value,
                TaskEventType.TASK_COMPLETED.value,
                TaskEventType.TASK_FAILED.value,
            ):
                logger.debug(f"Ignoring unknown event type: {event_type}")
                return

            event = TaskEvent(**event_dict)
            notification = TaskNotification(event=event)
            formatted = notification.format()

            logger.info(f"Task notification: {formatted}")
            await self._callback(formatted)

        except Exception as e:
            logger.error(f"Error processing event: {e}")
