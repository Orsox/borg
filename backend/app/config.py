import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./borgos.db"
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    initial_password: str = "borgborg"
    archon_path: str = "/opt/archon"
    archon_api_url: str = "http://localhost:3090"
    cors_origins: str = "http://localhost:5173"

    # Discord Bot Configuration
    discord_bot_enabled: bool = Field(default=False, description="Discord Bot aktivieren")
    discord_bot_token: str = Field(default="", description="Discord Bot Token")
    discord_bot_channel_id: Optional[int] = Field(default=None, description="Discord Channel ID")
    discord_bot_allowed_user_ids: str = Field(default="", description="Comma-separated Discord User IDs")
    discord_bot_prefix: str = Field(default="!", description="Message Prefix")
    discord_bot_mention_prefix: str = Field(default="@Locutus", description="@-Erwähnung Prefix")
    discord_bot_llm_base_url: str = Field(default="http://localhost:1234/v1", description="LM Studio API URL")
    discord_bot_llm_model_id: str = Field(default="google/gemma-4-e4b", description="LM Studio Modell-ID")

    # Locutus Autonomy
    locutus_dreaming_interval_minutes: int = Field(
        default=360,
        description="Minutes between automatic Locutus dreaming consolidation cycles",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def discord_bot_allowed_user_ids_list(self) -> list[int]:
        if not self.discord_bot_allowed_user_ids.strip():
            return []
        return [
            int(uid.strip())
            for uid in self.discord_bot_allowed_user_ids.split(",")
            if uid.strip()
        ]


settings = Settings()
