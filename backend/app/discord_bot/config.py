"""
Locutus-Konfiguration.

Liest Settings aus Environment Variables und pydantic-settings.
"""

import os
from typing import Optional

from pydantic import BaseModel, Field


class LlmConfig(BaseModel):
    """LM Studio Konfiguration für KI-Chat."""

    base_url: str = Field(default="http://localhost:1234/v1", description="LM Studio API URL")
    model_id: str = Field(default="mellum2-12b-a2.5b-instruct", description="Modell-ID")
    context_window: int = Field(default=131072, description="Context Window in Tokens")
    max_tokens: int = Field(default=2048, description="Max Output Tokens")
    temperature: float = Field(default=0.3, description="Temperature für deterministische Antworten")


class BotConfig(BaseModel):
    """Locutus Bot-Konfiguration."""

    enabled: bool = Field(default=False, description="Bot aktivieren/deaktivieren")
    token: str = Field(default="", description="Discord Bot Token")
    channel_id: Optional[int] = Field(default=None, description="Discord Channel ID (optional, None = alle Channels)")
    allowed_user_ids: Optional[list[int]] = Field(default=None, description="Erlaubte Discord User IDs (optional, None = alle)")
    prefix: str = Field(default="!", description="Message Prefix für Commands")
    mention_prefix: str = Field(default="@Locutus", description="@-Erwähnung Prefix")

    llm: LlmConfig = Field(default_factory=LlmConfig, description="LM Studio Konfiguration")

    @classmethod
    def from_env(cls) -> "BotConfig":
        """Lade Config aus Environment Variables."""
        return cls(
            enabled=os.getenv("DISCORD_BOT_ENABLED", "false").lower() == "true",
            token=os.getenv("DISCORD_BOT_TOKEN", ""),
            channel_id=int(os.getenv("DISCORD_BOT_CHANNEL_ID", "0") or "0") or None,
            allowed_user_ids=[
                int(uid)
                for uid in os.getenv("DISCORD_BOT_ALLOWED_USER_IDS", "").split(",")
                if uid.strip()
            ] or None,
            prefix=os.getenv("DISCORD_BOT_PREFIX", "!"),
            mention_prefix=os.getenv("DISCORD_BOT_MENTION_PREFIX", "@Locutus"),
        )

    def validate(self) -> list[str]:
        """Validiere Config. Gibt Liste der Errors zurück (leer wenn OK)."""
        errors = []
        if self.enabled and not self.token:
            errors.append("DISCORD_BOT_TOKEN required when DISCORD_BOT_ENABLED=true")
        if self.channel_id is not None and self.channel_id <= 0:
            errors.append("DISCORD_BOT_CHANNEL_ID must be a positive integer")
        return errors
