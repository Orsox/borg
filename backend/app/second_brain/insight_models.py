"""Models for Improvement Insights — actionable lessons derived from failed actions."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImprovementInsight(Base):
    """A recurring failure pattern with a concrete improvement recommendation.

    Insights have a lifecycle (open → acknowledged → resolved) and a stable
    identity across regenerations via ``dedup_key`` so user decisions survive
    each dreaming cycle.
    """

    __tablename__ = "improvement_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # f"{category}:{workflow or '*'}" — upsert key across regenerations
    dedup_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)

    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workflow: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Most representative error message plus occurrence context
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Templated, actionable advice per category
    recommendation: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # JSON list of ActionMemory ids backing this insight, capped at 20
    evidence_refs: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # open | acknowledged | resolved
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="open", index=True
    )

    first_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

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
