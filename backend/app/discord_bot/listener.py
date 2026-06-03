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
