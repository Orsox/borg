"""Models for the Peer Sync module.

Three tables:
  - PeerInstance: a registered remote BorgOS we can pull a manifest from.
  - SyncRun: one diff session against a peer (survives a UI reload).
  - SyncItemRecord: one differing item + Seven's analysis + the operator decision.

New tables only — no DDL migration block needed in main.py; Base.metadata.create_all
builds them once the models are imported.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PeerInstance(Base):
    """A registered remote BorgOS instance to sync from (pull + review)."""

    __tablename__ = "peer_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    base_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    # The remote's PEER_SYNC_TOKEN, sent as bearer when pulling its manifest.
    token: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SyncRun(Base):
    """One diff session against a peer."""

    __tablename__ = "peer_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    peer_id: Mapped[int] = mapped_column(
        ForeignKey("peer_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "diffed" → static diff done; "compared" → Seven analysed changed items.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="diffed")
    counts_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SyncItemRecord(Base):
    """One differing item within a SyncRun.

    `status` is the static-diff classification: only_remote / only_local / changed.
    `decision` is the operator's review verdict: pending / accepted / rejected /
    applied.
    """

    __tablename__ = "peer_sync_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("peer_sync_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    identity: Mapped[str] = mapped_column(String(1024), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    local_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    remote_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Stored so apply doesn't need to re-fetch; local kept for the review side-by-side.
    local_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    remote_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    analysis_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
