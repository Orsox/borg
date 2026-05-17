from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON array
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

    # Relationships
    outgoing_links: Mapped[list["NoteLink"]] = relationship(
        "NoteLink",
        back_populates="source",
        foreign_keys="NoteLink.source_id",
        cascade="all, delete-orphan",
    )
    incoming_links: Mapped[list["NoteLink"]] = relationship(
        "NoteLink",
        back_populates="target",
        foreign_keys="NoteLink.target_id",
        cascade="all, delete-orphan",
    )


class NoteLink(Base):
    __tablename__ = "note_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    source: Mapped["Note"] = relationship(
        "Note", back_populates="outgoing_links", foreign_keys=[source_id]
    )
    target: Mapped["Note"] = relationship(
        "Note", back_populates="incoming_links", foreign_keys=[target_id]
    )


class NoteSearch(Base):
    """FTS5 virtual table for full-text search on notes."""
    __tablename__ = "note_search"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String(512))
    content: Mapped[Optional[str]] = mapped_column(Text)
