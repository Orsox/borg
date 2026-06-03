"""
Locutus Datenmodelle.

Pydantic-Models für Commands, Responses und Event-Strukturen.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class CommandType(str, Enum):
    """Command-Typen die Locutus unterstützt."""

    CHAT = "chat"
    SEARCH = "search"
    STATUS = "status"
    CREATE_NOTE = "create_note"
    HELP = "help"


class TaskEventType(str, Enum):
    """SSE-Task-Event-Typen."""

    TASK_STARTED = "task_run_started"
    TASK_COMPLETED = "task_run_completed"
    TASK_FAILED = "task_run_failed"


class Command(BaseModel):
    """Parsed Discord Command."""

    content: str
    user_id: int
    channel_id: int
    command_type: Optional[CommandType] = None
    args: list[str] = []
    is_mention: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Response(BaseModel):
    """Locutus Antwort an Discord."""

    content: str
    is_error: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def format(self) -> str:
        """Formatiere Antwort für Discord (knapp & technisch)."""
        prefix = "⚠ ERROR" if self.is_error else "ℹ INFO"
        return f"[{prefix}] {self.content}"


class TaskEvent(BaseModel):
    """SSE Task-Event für Notifications."""

    type: TaskEventType
    task_id: int
    task_name: str
    run_id: int
    timestamp: str
    status: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None


class TaskNotification(BaseModel):
    """Formatierte Notification für Discord."""

    event: TaskEvent

    def format(self) -> str:
        """Formatiere Notification für Discord."""
        if self.event.type == TaskEventType.TASK_STARTED:
            return f"▶ Task `{self.event.task_name}` (#{self.event.run_id}) gestartet."
        elif self.event.type == TaskEventType.TASK_COMPLETED:
            dur = f"{self.event.duration_ms // 1000}s" if self.event.duration_ms else "?"
            return f"✓ Task `{self.event.task_name}` (#{self.event.run_id}) fertig. Dauer: {dur}."
        elif self.event.type == TaskEventType.TASK_FAILED:
            err = f" — {self.event.error}" if self.event.error else ""
            return f"✗ Task `{self.event.task_name}` (#{self.event.run_id}) fehlgeschlagen.{err}"
        return f"? Unbekanntes Event: {self.event.type}"
