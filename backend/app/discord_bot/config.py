"""
Locutus-Konfiguration.

Liest Settings aus Environment Variables und pydantic-settings.
"""

from typing import Optional

from pydantic import BaseModel, Field

from app.config import settings


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
        """
        Lade Config aus den zentralen BorgOS Settings.

        Wichtig: ``settings`` lädt ``backend/.env`` via pydantic-settings. Ein
        direkter Zugriff über ``os.getenv`` sieht diese Werte nicht, solange sie
        nicht zusätzlich in der Shell exportiert wurden.
        """
        return cls(
            enabled=settings.discord_bot_enabled,
            token=settings.discord_bot_token,
            channel_id=settings.discord_bot_channel_id,
            allowed_user_ids=settings.discord_bot_allowed_user_ids_list or None,
            prefix=settings.discord_bot_prefix,
            mention_prefix=settings.discord_bot_mention_prefix,
            llm=LlmConfig(
                base_url=settings.discord_bot_llm_base_url if hasattr(settings, "discord_bot_llm_base_url") else "http://localhost:1234/v1",
                model_id=settings.discord_bot_llm_model_id,
            ),
        )

    def validate(self) -> list[str]:
        """Validiere Config. Gibt Liste der Errors zurück (leer wenn OK)."""
        errors = []
        if self.enabled and not self.token:
            errors.append("DISCORD_BOT_TOKEN required when DISCORD_BOT_ENABLED=true")
        if self.channel_id is not None and self.channel_id <= 0:
            errors.append("DISCORD_BOT_CHANNEL_ID must be a positive integer")
        return errors
