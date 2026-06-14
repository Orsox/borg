"""Pydantic schemas for persona API endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Embedded config sub-models ─────────────────────────────────────


class LlmConfigSchema(BaseModel):
    """LLM settings for a single persona."""

    base_url: str = Field(
        default="http://localhost:1234/v1",
        description="LLM API base URL",
    )
    model_id: str = Field(default="", description="Model identifier")
    context_window: int = Field(default=131072, ge=256, le=1_048_576)
    max_tokens: int = Field(default=2048, ge=64, le=131_072)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)


class DiscordConfigSchema(BaseModel):
    """Discord bot account settings for a single persona."""

    enabled: bool = Field(default=False)
    token: Optional[str] = Field(default=None, description="Bot token (sensitive)")
    channel_id: Optional[int] = Field(default=None)
    allowed_user_ids: Optional[str] = Field(
        default=None, description="Comma-separated Discord user IDs",
    )
    prefix: str = Field(default="!")
    mention_prefix: str = Field(default="")


# ── Request schemas ────────────────────────────────────────────────


class PersonaCreate(BaseModel):
    """Request body for creating a new persona."""

    key: str = Field(..., min_length=1, max_length=64, pattern="^[a-z0-9_-]+$")
    display_name: str = Field(..., min_length=1, max_length=128)
    color: Optional[str] = Field(default=None, max_length=16)
    system_prompt: Optional[str] = Field(default=None)

    llm: LlmConfigSchema = Field(default_factory=LlmConfigSchema)
    discord: DiscordConfigSchema = Field(default_factory=DiscordConfigSchema)

    is_active: bool = Field(default=True)
    include_in_meetings: bool = Field(default=True)


class PersonaUpdate(BaseModel):
    """Partial update for an existing persona (all fields optional)."""

    key: Optional[str] = Field(default=None, min_length=1, max_length=64, pattern="^[a-z0-9_-]+$")
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    color: Optional[str] = Field(default=None, max_length=16)
    system_prompt: Optional[str] = Field(default=None)

    llm: Optional[LlmConfigSchema] = Field(default=None)
    discord: Optional[DiscordConfigSchema] = Field(default=None)

    is_active: Optional[bool] = Field(default=None)
    include_in_meetings: Optional[bool] = Field(default=None)


# ── Response schemas ───────────────────────────────────────────────


class PersonaResponse(BaseModel):
    """Full persona detail returned by GET /api/personas/{id}."""

    id: int
    key: str
    display_name: str
    color: Optional[str]
    system_prompt: Optional[str]

    llm: LlmConfigSchema
    discord: DiscordConfigSchema

    is_active: bool
    include_in_meetings: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PersonaListItem(BaseModel):
    """Lightweight persona for list views (excludes system_prompt text)."""

    id: int
    key: str
    display_name: str
    color: Optional[str]
    llm_model_id: str
    discord_enabled: bool
    is_active: bool
    include_in_meetings: bool
    created_at: datetime
    updated_at: datetime


class PersonaListResponse(BaseModel):
    items: list[PersonaListItem]
    total: int
