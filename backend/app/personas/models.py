"""SQLAlchemy models for persona definitions."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Persona(Base):
    """A character (persona) managed by BorgOS.

    Replaces the previous .env-only persona configuration with a persistent,
    web-editable database record. Each row carries LLM settings, Discord bot
    account config, and the full system prompt text for that character.

    Consumers read this table at startup to build their runtime configs:
    - discord_bot creates LlmClient instances per persona's llm_* columns
    - meeting builds its participant list from active personas with include_in_meetings=True
    """

    __tablename__ = "personas"

    # ── Identity ────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)

    # ── Display metadata ────────────────────────────────────────
    color: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, default=None)

    # ── System prompt ───────────────────────────────────────────
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)

    # ── LLM configuration ──────────────────────────────────────
    llm_base_url: Mapped[str] = mapped_column(String(512), nullable=False, default="http://localhost:1234/v1")
    llm_model_id: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    llm_context_window: Mapped[int] = mapped_column(Integer, nullable=False, default=131072)
    llm_max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=2048)
    llm_temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)

    # ── Discord bot account config ──────────────────────────────
    discord_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    discord_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    discord_channel_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    discord_allowed_user_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    discord_prefix: Mapped[str] = mapped_column(String(16), nullable=False, default="!")
    discord_mention_prefix: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    # ── Flags ───────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_in_meetings: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Timestamps ──────────────────────────────────────────────
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
