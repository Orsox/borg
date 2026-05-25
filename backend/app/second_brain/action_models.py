"""Models for Action Memory — tracks performed actions in the Second Brain."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ActionMemory(Base):
    """Records a performed action: what was done, how, and whether it succeeded."""

    __tablename__ = "action_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Type of action (e.g., "presentation_creation", "document_generation", "data_analysis")
    action_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="general", index=True
    )

    # Tools/skills used (JSON array as text, e.g., ["python-pptx", "SQLAlchemy"])
    tools_used: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Status: success, failed, in_progress
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="success", index=True
    )

    # Whether this action is archived (soft-delete)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # Duration of the action in milliseconds (optional)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Path to output artifact (optional, e.g., "/path/to/output.pptx")
    output_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # Additional metadata (JSON, e.g., {"slide_count": 13, "venv": "true"})
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Tags for categorization and filtering
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Optional external linkage for idempotent sync/import jobs
    source_kind: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    source_ref: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, index=True)

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
