"""Models for Task Automation module."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="shell", index=True
    )  # 'shell', 'archon_workflow', 'heartbeat', or 'skill'
    schedule: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # cron expression
    command: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    archon_workflow_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    archon_workflow_template: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True, default=None
    )  # For skill-type tasks: which workflow template to use
    heartbeat_workflow_name: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True, default=None
    )  # For heartbeat-type tasks: which workflow to trigger on heartbeat turn
    dreaming_days: Mapped[int] = mapped_column(Integer, default=14, nullable=False)  # For dreaming-type tasks: days to look back
    dreaming_min_actions: Mapped[int] = mapped_column(Integer, default=5, nullable=False)  # For dreaming-type tasks: minimum actions required
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    retry_max: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_delay: Mapped[int] = mapped_column(Integer, default=60, nullable=False)  # seconds
    timeout: Mapped[int] = mapped_column(Integer, default=300, nullable=False)  # seconds
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

    runs: Mapped[list["TaskRun"]] = relationship(
        "TaskRun",
        back_populates="task",
        cascade="all, delete-orphan",
    )


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="running", index=True
    )  # running, success, failed, timeout
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stdout: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stderr: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    task: Mapped["Task"] = relationship("Task", back_populates="runs")
