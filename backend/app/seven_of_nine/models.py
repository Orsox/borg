"""Models for the Seven of Nine module — persona, memory, and audit trail."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DroneProfile(Base):
    """Stores the canonical persona description for Seven of Nine."""

    __tablename__ = "seven_of_nine_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class DroneMemoryEntry(Base):
    """Personal memory entries — facts Seven of Nine has been told to retain."""

    __tablename__ = "seven_of_nine_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general", index=True)
    # e.g., "general", "user-instruction", "project-feeling", "interaction"
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class DroneAuditEntry(Base):
    """Append-only record of mutating actions Seven of Nine performs."""

    __tablename__ = "seven_of_nine_audit_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # Who performed the action: "seven_of_nine", "user", "discord_bot", ...
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="seven_of_nine", index=True)
    # What happened, e.g. "drone_memory_create"
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # What it acted on — record id, etc.
    target: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    payload_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Outcome: "ok", "error", "denied"
    result: Mapped[str] = mapped_column(String(16), nullable=False, default="ok", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
