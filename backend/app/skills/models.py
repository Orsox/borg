"""Models for the Skills module."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    archon_workflow_file: Mapped[str] = mapped_column(
        String(512), nullable=False, default=""
    )  # Path to generated YAML in .archon/workflows/
    model: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    # Default model for nodes in the generated workflow
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Whether this skill is enabled for execution
    category: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # Human-readable category: "automation", "review", "analysis", etc.
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

    # Note: no back-reference to Task model — skills are independent of the
    # task_automation module. A Task of type='skill' can reference a Skill
    # by name, but no ORM relationship is defined between them.
