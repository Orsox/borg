from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ArchonAsset(Base):
    __tablename__ = "archon_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown", index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON array stored as text
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True, index=True)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_scanned: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class CopyHistory(Base):
    __tablename__ = "copy_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    asset_name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    destination_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    copied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
