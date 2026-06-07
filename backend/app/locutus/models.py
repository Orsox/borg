"""Models for Locutus module — persona, memory, evolution tracking."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CharacterProfile(Base):
    """Stores the canonical Character.md content and metadata."""

    __tablename__ = "locutus_character_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    file_path: Mapped[str] = mapped_column(
        String(1024), nullable=False, default="~/.locutus/Character.md"
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
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


class CharacterMemoryEntry(Base):
    """Personal memory entries — user preferences, past interactions, feelings about projects."""

    __tablename__ = "locutus_character_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general", index=True)
    # e.g., "general", "user-preference", "project-feeling", "interaction"
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


class ReasoningLog(Base):
    """Evidence Locutus uses to justify evolution decisions before creating skills/agents."""

    __tablename__ = "locutus_reasoning_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    # 1. The specific memory/failure that triggered the need
    trigger_description: Mapped[str] = mapped_column(Text, nullable=False)
    # 2. The proposed technical solution
    proposed_solution: Mapped[str] = mapped_column(Text, nullable=False)
    # 3. The expected outcome
    expected_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    # Status: draft, approved, implemented, rejected
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    # Optional linkage to the ActionMemory entry that triggered this
    trigger_action_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    # Optional: path to the created skill file (if implemented)
    created_skill_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
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


class EvolutionBudget(Base):
    """Weekly resource budget for autonomous evolution (skills + agents per week)."""

    __tablename__ = "locutus_evolution_budgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Max skills Locutus can create per week
    max_skills_per_week: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    # Max agents Locutus can create per week
    max_agents_per_week: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    # Skills created in current week (reset weekly)
    skills_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Agents created in current week (reset weekly)
    agents_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Week start date (for tracking/reset logic)
    week_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    # Whether evolution is currently active
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Whether redundancy check is enabled before skill creation
    redundancy_check_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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

    @property
    def skills_remaining(self) -> int:
        """Return the remaining skill-creation budget for the current week."""
        return max(0, self.max_skills_per_week - self.skills_created)

    @property
    def agents_remaining(self) -> int:
        """Return the remaining agent-creation budget for the current week."""
        return max(0, self.max_agents_per_week - self.agents_created)


class SkillRecord(Base):
    """Tracks skills created by Locutus — both filesystem and DB record."""

    __tablename__ = "locutus_skill_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Path to the SKILL.md file on disk
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Status: draft, active, deprecated
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    # Optional: reasoning log that led to this skill
    reasoning_log_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("locutus_reasoning_logs.id", ondelete="SET NULL"), nullable=True
    )
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

    reasoning_log: Mapped[Optional["ReasoningLog"]] = relationship("ReasoningLog")
