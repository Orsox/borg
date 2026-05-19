"""SQLAlchemy mirror models for Archon system data."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ArchonSystemHealth(Base):
    __tablename__ = "archon_system_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[Optional[str]] = mapped_column(String(64))
    adapter: Mapped[Optional[str]] = mapped_column(String(32))
    is_docker: Mapped[bool] = mapped_column(Boolean, default=False)
    running_workflows: Mapped[int] = mapped_column(Integer, default=0)
    active_platforms: Mapped[str] = mapped_column(Text, default="[]")
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class ArchonRun(Base):
    __tablename__ = "archon_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    archon_run_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    workflow_name: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32))
    user_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[str]] = mapped_column(String(64))
    last_activity_at: Mapped[Optional[str]] = mapped_column(String(64))
    completed_at: Mapped[Optional[str]] = mapped_column(String(64))
    codebase_name: Mapped[Optional[str]] = mapped_column(String(256))
    working_path: Mapped[Optional[str]] = mapped_column(String(1024))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArchonCodebase(Base):
    __tablename__ = "archon_codebases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    archon_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    repository_url: Mapped[Optional[str]] = mapped_column(String(1024))
    default_branch: Mapped[Optional[str]] = mapped_column(String(64))
    ai_assistant_type: Mapped[Optional[str]] = mapped_column(String(32))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArchonWorkflowMeta(Base):
    __tablename__ = "archon_workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    provider: Mapped[Optional[str]] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32), default="unknown")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
