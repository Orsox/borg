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

    # Discord Bot Configuration — Locutus (primäre Persona, eigener Account)
    discord_bot_locutus_enabled: bool = Field(default=False, description="Locutus Bot aktivieren")
    discord_bot_locutus_token: str = Field(default="", description="Discord Bot Token für Locutus")
    discord_bot_locutus_channel_id: Optional[int] = Field(default=None, description="Discord Channel ID für Locutus")
    discord_bot_locutus_allowed_user_ids: str = Field(default="", description="Comma-separated Discord User IDs für Locutus")
    discord_bot_locutus_prefix: str = Field(default="!", description="Message Prefix für Locutus")
    discord_bot_locutus_mention_prefix: str = Field(default="@Locutus", description="@-Erwähnung Prefix für Locutus")
    discord_bot_locutus_llm_base_url: str = Field(default="http://localhost:1234/v1", description="LM Studio API URL für Locutus")
    discord_bot_locutus_llm_model_id: str = Field(default="google/gemma-4-e4b", description="LM Studio Modell-ID für Locutus")

    # Seven of Nine — eigener Discord-Bot-Account (eigenes Token), zweite Persona,
    # zweites LM Studio Modell
    discord_bot_seven_enabled: bool = Field(default=False, description="Seven of Nine Bot aktivieren")
    discord_bot_seven_token: str = Field(default="", description="Discord Bot Token für Seven of Nine")
    discord_bot_seven_channel_id: Optional[int] = Field(default=None, description="Discord Channel ID für Seven of Nine")
    discord_bot_seven_allowed_user_ids: str = Field(default="", description="Comma-separated Discord User IDs für Seven of Nine")
    discord_bot_seven_prefix: str = Field(default="!", description="Message Prefix für Seven of Nine")
    discord_bot_seven_mention_prefix: str = Field(default="@Seven of Nine", description="@-Erwähnung Prefix für Seven of Nine")
    discord_bot_seven_llm_base_url: str = Field(default="http://localhost:1234/v1", description="LM Studio API URL für Seven of Nine")
    discord_bot_seven_llm_model_id: str = Field(default="qwen/qwen3.6-35b-a3b-mtp", description="LM Studio Modell-ID für Seven of Nine")

    # Seven of Nine — eigenes GitLab-Konto (selbst gehostete Instanz). Agent Mode
    # klont/committet/pusht in ihrem eigenen Workspace und kann neue Projekte
    # unter ihrem Account anlegen. Provisionierung ist eine externe, einmalige
    # Handlung (wie discord_bot_seven_token) — der Code legt nie selbst Konten an.
    # PAT erzeugen: GitLab → Sevens Account → Settings → Access Tokens, Scopes
    # `api` + `read_repository` + `write_repository`.
    # Empirisch verifiziert (docker compose exec backend ...): `http://gitlab`
    # liefert eine TLS-Redirect-Antwort mit selbstsigniertem Zertifikat — die
    # omnibus-Instanz erzwingt HTTPS. Daher https:// als Default; git/httpx-Calls
    # in agent_sandbox.service deaktivieren die Zertifikatsprüfung entsprechend
    # (sslVerify=false / verify=False) statt das selbstsignierte Cert zu vertrauen.
    seven_gitlab_url: str = Field(default="https://gitlab", description="Interne GitLab-URL (vom Backend aus erreichbar, selbstsigniertes Zertifikat — TLS-Verifikation wird im Code deaktiviert)")
    seven_gitlab_token: str = Field(default="", description="Personal Access Token für Sevens GitLab-Konto (Scopes: api, read_repository, write_repository)")
    seven_gitlab_username: str = Field(default="seven-of-nine", description="GitLab-Benutzername für Sevens Konto")
    seven_gitlab_workspace_repo: str = Field(default="workspace", description="Default-Repo für Agent-Mode-Läufe")

    # Locutus Autonomy — Dreaming
    locutus_dreaming_time: str = Field(
        default="03:00",
        description="Time to run dreaming (HH:MM)",
    )
    locutus_dreaming_frequency: str = Field(
        default="daily",
        description="Frequency of dreaming: 'hourly', 'daily', 'weekly', 'every_6_hours', 'every_12_hours'",
        pattern="^(hourly|daily|weekly|every_6_hours|every_12_hours)$",
    )
    locutus_dreaming_days: int = Field(
        default=14,
        description="Number of days to look back for ActionMemory entries",
    )
    locutus_dreaming_min_actions: int = Field(
        default=5,
        description="Minimum ActionMemory entries required to trigger dreaming",
    )

    # Seven of Nine — Dreaming
    seven_dreaming_time: str = Field(
        default="04:00",
        description="Time to run dreaming (HH:MM)",
    )
    seven_dreaming_frequency: str = Field(
        default="daily",
        description="Frequency of dreaming: 'hourly', 'daily', 'weekly', 'every_6_hours', 'every_12_hours'",
        pattern="^(hourly|daily|weekly|every_6_hours|every_12_hours)$",
    )
    seven_dreaming_days: int = Field(
        default=14,
        description="Number of days to look back for ActionMemory entries",
    )
    seven_dreaming_min_actions: int = Field(
        default=5,
        description="Minimum ActionMemory entries required to trigger dreaming",
    )

    # Observability — Langfuse (self-hosted, optional). Default off: the app
    # must behave identically without Langfuse running (tests, degraded mode).
    langfuse_enabled: bool = Field(default=False, description="Langfuse-Tracing aktivieren")
    langfuse_host: str = Field(default="http://langfuse-web:3000", description="Langfuse-Server-URL (vom Backend aus erreichbar)")
    langfuse_public_key: str = Field(default="", description="Langfuse Project Public Key (pk-lf-...)")
    langfuse_secret_key: str = Field(default="", description="Langfuse Project Secret Key (sk-lf-...)")
    langfuse_ui_url: str = Field(default="", description="Öffentliche Langfuse-UI-URL für Links (z.B. http://homelab:3052)")
    langfuse_project_id: str = Field(default="borg", description="Langfuse-Projekt-ID (Headless-Init in observability/docker-compose.yml)")
    # LiteLLM-Proxy für Agent Mode: pi's models.json zeigt hierauf, damit jede
    # LLM-Anfrage aus der Sandbox in Langfuse landet. Leer = direkt zu LM Studio.
    agent_mode_llm_proxy_url: str = Field(default="", description="LiteLLM-Proxy-URL für pi (leer = direkt zu LM Studio)")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def discord_bot_locutus_allowed_user_ids_list(self) -> list[int]:
        if not self.discord_bot_locutus_allowed_user_ids.strip():
            return []
        return [
            int(uid.strip())
            for uid in self.discord_bot_locutus_allowed_user_ids.split(",")
            if uid.strip()
        ]

    @property
    def discord_bot_seven_allowed_user_ids_list(self) -> list[int]:
        if not self.discord_bot_seven_allowed_user_ids.strip():
            return []
        return [
            int(uid.strip())
            for uid in self.discord_bot_seven_allowed_user_ids.split(",")
            if uid.strip()
        ]


settings = Settings()
