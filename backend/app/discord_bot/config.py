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

    env_prefix: str = Field(default="DISCORD_BOT", description="Präfix der Env-Vars (für Fehlermeldungen)")
    enabled: bool = Field(default=False, description="Bot aktivieren/deaktivieren")
    token: str = Field(default="", description="Discord Bot Token")
    channel_id: Optional[int] = Field(default=None, description="Discord Channel ID (optional, None = alle Channels)")
    allowed_user_ids: Optional[list[int]] = Field(default=None, description="Erlaubte Discord User IDs (optional, None = alle)")
    prefix: str = Field(default="!", description="Message Prefix für Commands")
    mention_prefix: str = Field(default="@Locutus", description="@-Erwähnung Prefix")

    llm: LlmConfig = Field(default_factory=LlmConfig, description="LM Studio Konfiguration (Locutus)")
    seven_llm: LlmConfig = Field(default_factory=LlmConfig, description="LM Studio Konfiguration (Seven of Nine)")

    @classmethod
    def from_env_locutus(cls) -> "BotConfig":
        """
        Lade Locutus' Config (inkl. beider LLM-Configs für den geteilten Service)
        aus den zentralen BorgOS Settings.

        Wichtig: ``settings`` lädt ``backend/.env`` via pydantic-settings. Ein
        direkter Zugriff über ``os.getenv`` sieht diese Werte nicht, solange sie
        nicht zusätzlich in der Shell exportiert wurden.
        """
        return cls(
            env_prefix="DISCORD_BOT_LOCUTUS",
            enabled=settings.discord_bot_locutus_enabled,
            token=settings.discord_bot_locutus_token,
            channel_id=settings.discord_bot_locutus_channel_id,
            allowed_user_ids=settings.discord_bot_locutus_allowed_user_ids_list or None,
            prefix=settings.discord_bot_locutus_prefix,
            mention_prefix=settings.discord_bot_locutus_mention_prefix,
            llm=LlmConfig(
                base_url=settings.discord_bot_locutus_llm_base_url,
                model_id=settings.discord_bot_locutus_llm_model_id,
            ),
            seven_llm=LlmConfig(
                base_url=settings.discord_bot_seven_llm_base_url,
                model_id=settings.discord_bot_seven_llm_model_id,
            ),
        )

    @classmethod
    def from_env_seven(cls) -> "BotConfig":
        """
        Lade die Verbindungs-Config für Seven of Nines eigenen Discord-Bot-Account.

        Seven loggt sich mit ihrem eigenen Token ein (separater Discord-Bot,
        kein geteilter Account mit Locutus) — dadurch funktionieren echte
        @-Erwähnungen für sie nativ.
        """
        return cls(
            env_prefix="DISCORD_BOT_SEVEN",
            enabled=settings.discord_bot_seven_enabled,
            token=settings.discord_bot_seven_token,
            channel_id=settings.discord_bot_seven_channel_id,
            allowed_user_ids=settings.discord_bot_seven_allowed_user_ids_list or None,
            prefix=settings.discord_bot_seven_prefix,
            mention_prefix=settings.discord_bot_seven_mention_prefix,
            llm=LlmConfig(
                base_url=settings.discord_bot_seven_llm_base_url,
                model_id=settings.discord_bot_seven_llm_model_id,
            ),
        )

    def validate(self) -> list[str]:
        """Validiere Config. Gibt Liste der Errors zurück (leer wenn OK)."""
        errors = []
        if self.enabled and not self.token:
            errors.append(f"{self.env_prefix}_TOKEN required when {self.env_prefix}_ENABLED=true")
        if self.channel_id is not None and self.channel_id <= 0:
            errors.append(f"{self.env_prefix}_CHANNEL_ID must be a positive integer")
        return errors
