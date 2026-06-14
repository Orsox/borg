import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.archon_hub.models import ArchonAsset, CopyHistory  # noqa: F401
from app.archon_hub.router import router as archon_router
from app.archon_system.models import ArchonSystemHealth, ArchonRun, ArchonCodebase, ArchonWorkflowMeta  # noqa: F401
from app.archon_system.router import router as archon_system_router
from app.vault.router import router as vault_router
from app.auth.models import User  # noqa: F401 — ensures model is registered
from app.auth.router import router as auth_router, users_router
from app.second_brain.models import Note, NoteLink  # noqa: F401
from app.second_brain.action_models import ActionMemory  # noqa: F401
from app.second_brain.insight_models import ImprovementInsight  # noqa: F401
from app.second_brain.router import router as brain_router
from app.second_brain.action_router import router as action_router
from app.second_brain.insight_router import router as insight_router
from app.second_brain import action_service as action_memory_service
from app.task_automation.models import Task, TaskRun  # noqa: F401
from app.locutus.models import CharacterProfile, CharacterMemoryEntry, ReasoningLog, EvolutionBudget, SkillRecord  # noqa: F401
from app.seven_of_nine.models import DroneProfile, DroneMemoryEntry, DroneAuditEntry  # noqa: F401
from app.peer_sync.models import PeerInstance, SyncRun, SyncItemRecord  # noqa: F401
from app.personas.models import Persona  # noqa: F401
from app.task_automation.router import router as task_router
from app.task_automation.scheduler import init_scheduler, shutdown_scheduler, reload_all_tasks
from app.skills.router import router as skills_router
from app.dreaming.router import router as dreaming_router
from app.auth.service import seed_default_user
from app.config import settings
from app.discord_bot.router import set_bot_service, router as discord_locutus_router
from app.locutus.router import router as locutus_router
from app.locutus import service as locutus_service
from app.seven_of_nine.router import router as seven_of_nine_router
from app.seven_of_nine import service as seven_of_nine_service
from app.agent_sandbox.router import router as agent_sandbox_router
from app.observability.router import router as observability_router
from app.peer_sync.router import router as peer_sync_router
from app.peer_sync.peer_router import router as peer_router
from app.discord_bot.config import BotConfig, LlmConfig
from app.discord_bot.service import DiscordBotService, PERSONA_LOCUTUS, PERSONA_SEVEN
from app.meeting.orchestrator import MeetingService
from app.meeting.router import router as meeting_router, set_meeting_service
from app.personas.router import router as personas_router
from app.discord_bot.listener import TaskEventListener
from app.discord_bot.bot import BotClient
from app.database import Base, AsyncSessionLocal, engine
from app.shared.exceptions import (
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

# Configure root logging so that app and library loggers (discord.py, apscheduler, ...)
# actually reach stdout — uvicorn only configures its own "uvicorn.*" loggers, leaving
# the root logger without a handler and our logger.info/warning/error calls invisible.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

START_TIME = time.time()
logger = logging.getLogger(__name__)

# Global references for Discord Bot lifecycle management
_bot_service: DiscordBotService | None = None
_sse_listener: TaskEventListener | None = None
_bot_client: BotClient | None = None
_bot_task: asyncio.Task | None = None
_seven_bot_client: BotClient | None = None
_seven_bot_task: asyncio.Task | None = None
_meeting_service: MeetingService | None = None


async def _connect_persona_bot(
    client: BotClient,
    config: BotConfig,
    persona_name: str,
    task_name: str,
) -> Optional[asyncio.Task]:
    """
    Verbinde einen bereits konstruierten Discord-BotClient mit seinem eigenen Token.

    Jede Persona (Locutus, Seven of Nine, ...) loggt sich als eigener
    Discord-Bot-Account ein — `config` enthält ihr eigenes Token, ihren
    eigenen Channel/Prefix etc.
    """
    errors = config.validate()
    if errors:
        logger.warning(f"{persona_name} bot config errors: {errors}")
        return None

    if not config.token:
        logger.warning(f"{config.env_prefix}_TOKEN is empty — not connecting {persona_name} to Discord")
        return None

    logger.info(f"Starting BotClient ({persona_name})...")
    task = asyncio.create_task(client.start(config.token), name=task_name)
    task.add_done_callback(_log_bot_task_result)
    await client.wait_until_ready(timeout=30.0)
    logger.info(f"Discord Bot '{persona_name}' initialized")
    return task


def _build_bot_config_from_personas(locutus_persona, seven_persona) -> BotConfig:
    """Build a shared BotConfig from DB persona rows (has both LLM configs)."""
    return BotConfig(
        env_prefix="DISCORD_BOT_LOCUTUS",
        enabled=locutus_persona.discord_enabled,
        token=locutus_persona.discord_token or "",
        channel_id=locutus_persona.discord_channel_id,
        allowed_user_ids=(
            [int(u.strip()) for u in locutus_persona.discord_allowed_user_ids.split(",") if u.strip()]
            if locutus_persona.discord_allowed_user_ids else None
        ),
        prefix=locutus_persona.discord_prefix,
        mention_prefix=locutus_persona.discord_mention_prefix or "",
        llm=LlmConfig(
            persona="locutus",
            base_url=locutus_persona.llm_base_url,
            model_id=locutus_persona.llm_model_id,
            context_window=locutus_persona.llm_context_window,
            max_tokens=locutus_persona.llm_max_tokens,
            temperature=float(locutus_persona.llm_temperature),
        ),
        seven_llm=LlmConfig(
            persona="seven",
            base_url=seven_persona.llm_base_url,
            model_id=seven_persona.llm_model_id,
            context_window=seven_persona.llm_context_window,
            max_tokens=seven_persona.llm_max_tokens,
            temperature=float(seven_persona.llm_temperature),
        ),
    )


def _build_seven_bot_config(seven_persona) -> BotConfig:
    """Build Seven's standalone BotConfig from DB persona row."""
    return BotConfig(
        env_prefix="DISCORD_BOT_SEVEN",
        enabled=seven_persona.discord_enabled,
        token=seven_persona.discord_token or "",
        channel_id=seven_persona.discord_channel_id,
        allowed_user_ids=(
            [int(u.strip()) for u in seven_persona.discord_allowed_user_ids.split(",") if u.strip()]
            if seven_persona.discord_allowed_user_ids else None
        ),
        prefix=seven_persona.discord_prefix,
        mention_prefix=seven_persona.discord_mention_prefix or "",
        llm=LlmConfig(
            persona="seven",
            base_url=seven_persona.llm_base_url,
            model_id=seven_persona.llm_model_id,
            context_window=seven_persona.llm_context_window,
            max_tokens=seven_persona.llm_max_tokens,
            temperature=float(seven_persona.llm_temperature),
        ),
    )


async def _init_discord_bot() -> None:
    """Initialisiere Locutus + Seven of Nine Discord-Bots — eigene Accounts, geteilter Service.

    Both personas have their own ``discord_enabled`` flag and bot token stored in
    the personas DB table. They share a ``DiscordBotService`` (LLM-Clients,
    Memory, Audit, Notes-Zugriff).
    """
    global _bot_service, _sse_listener, _bot_client, _bot_task, _seven_bot_client, _seven_bot_task

    # Load persona configs from DB — falls back to .env if table is empty.
    async with AsyncSessionLocal() as db:
        locutus_persona = await app.personas.service.get_persona_by_key(db, "locutus")  # type: ignore[attr-defined]
        seven_persona = await app.personas.service.get_persona_by_key(db, "seven")  # type: ignore[attr-defined]

    if locutus_persona is not None and seven_persona is not None:
        locutus_config = _build_bot_config_from_personas(locutus_persona, seven_persona)
        seven_config = _build_seven_bot_config(seven_persona)
    else:
        # Fallback to .env (should only happen before seed runs)
        logger.warning("No personas found in DB — falling back to .env config for Discord bots")
        locutus_config = BotConfig.from_env_locutus()
        seven_config = BotConfig.from_env_seven()

    if not locutus_config.enabled and not seven_config.enabled:
        logger.info(
            "Discord Bots disabled (DISCORD_BOT_LOCUTUS_ENABLED and DISCORD_BOT_SEVEN_ENABLED both false)"
        )
        return

    try:
        # Service initialisieren — geteilt von Locutus und Seven of Nine, braucht
        # daher beide LLM-Configs unabhängig davon, welche Persona(s) aktiv sind.
        _bot_service = DiscordBotService(locutus_config)
        await _bot_service.start()
        set_bot_service(_bot_service)

        if locutus_config.enabled:
            _bot_client = BotClient(
                config=locutus_config,
                service=_bot_service,
                persona_name="Locutus",
                persona_key=PERSONA_LOCUTUS,
                chat_fn=_bot_service.chat,
            )

            _bot_task = await _connect_persona_bot(_bot_client, locutus_config, "Locutus", "locutus-bot")
        else:
            logger.info("Locutus bot disabled (DISCORD_BOT_LOCUTUS_ENABLED=false)")

        if seven_config.enabled:
            _seven_bot_client = BotClient(
                config=seven_config,
                service=_bot_service,
                persona_name="Seven of Nine",
                persona_key=PERSONA_SEVEN,
                chat_fn=_bot_service.chat_as_seven,
            )

            # Agent-Mode-Ergebnisse (Hintergrund-Runs, siehe DiscordBotService.
            # run_agent_task) gehen als Folge-Notification an Sevens Channel —
            # gleiche Verdrahtung wie der notification_callback oben für Locutus.
            async def seven_notifier(content: str) -> None:
                if _seven_bot_client and _seven_bot_client.is_ready():
                    await _seven_bot_client.send_notification(content)
                else:
                    logger.info(f"Seven notification (bot not ready): {content}")

            _bot_service.set_seven_notifier(seven_notifier)

            _seven_bot_task = await _connect_persona_bot(
                _seven_bot_client, seven_config, "Seven of Nine", "seven-of-nine-bot"
            )
        else:
            logger.info("Seven of Nine bot disabled (DISCORD_BOT_SEVEN_ENABLED=false)")

        # Persona-zu-Persona-Dialog: Nur wenn beide Bots laufen, akzeptieren
        # sie gegenseitig ihre Nachrichten (Namens-Adressierung + Turn-Budget,
        # siehe BotClient.on_message). Alle anderen Bots bleiben ignoriert.
        if _bot_client and _seven_bot_client:
            _bot_client.set_peer(_seven_bot_client)
            _seven_bot_client.set_peer(_bot_client)
            logger.info("Persona peer link established: Locutus ↔ Seven of Nine")

        # SSE-Listener: Task-/Dreaming-Notifications gehen an den Bot der
        # Persona, in deren Namen das Event läuft (z.B. Sevens Dreaming-Zyklus
        # meldet Seven selbst). Ohne Persona — oder wenn deren Bot nicht
        # läuft — übernimmt der jeweils andere Bot als Relay.
        async def notification_callback(content: str, persona: Optional[str] = None) -> None:
            """Callback für Task-Notifications — Routing nach Persona."""
            primary = _seven_bot_client if persona == PERSONA_SEVEN else _bot_client
            fallback = _bot_client if primary is _seven_bot_client else _seven_bot_client
            if primary and primary.is_ready():
                await primary.send_notification(content)
            elif fallback and fallback.is_ready():
                await fallback.send_notification(content)
            else:
                logger.info(f"Notification (no bot ready): {content}")

        _sse_listener = TaskEventListener(notification_callback)
        await _sse_listener.start()
    except Exception as e:
        logger.error(f"Failed to initialize Discord Bot: {e}")


def _log_bot_task_result(task: asyncio.Task) -> None:
    """Logge Discord-Bot-Startfehler aus dem Hintergrund-Task."""
    if task.cancelled():
        return
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc:
        logger.error("Discord Bot task failed", exc_info=exc)


async def _close_persona_bot(client: BotClient | None, task: asyncio.Task | None, persona_name: str) -> None:
    """Schließe BotClient-Verbindung und beende den Hintergrund-Task einer Persona."""
    if client:
        await client.close()
        logger.info(f"BotClient ({persona_name}) closed")

    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info(f"BotClient ({persona_name}) task cancelled")


async def _shutdown_discord_bot() -> None:
    """Shutdown Locutus + Seven of Nine Discord-Bots."""
    global _bot_service, _sse_listener, _bot_client, _bot_task, _seven_bot_client, _seven_bot_task

    if _sse_listener:
        await _sse_listener.stop()
        logger.info("TaskEventListener stopped")

    await _close_persona_bot(_bot_client, _bot_task, "Locutus")
    await _close_persona_bot(_seven_bot_client, _seven_bot_task, "Seven of Nine")

    if _bot_service:
        await _bot_service.stop()
        logger.info("DiscordBotService stopped")


def _ensure_db_dir() -> None:
    db_url = settings.database_url
    if "sqlite" in db_url:
        # Extract file path from URL like sqlite+aiosqlite:///path/to/file.db
        path_part = db_url.split("///")[-1]
        if path_part and path_part != ":memory:":
            db_path = Path(path_part).expanduser().resolve()
            db_path.parent.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_db_dir()
    # Create all tables + DDL migration for new columns
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add is_admin / is_active columns if missing (SQLite migration)
        for ddl in [
            "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1",
            "ALTER TABLE tasks ADD COLUMN archon_workflow_template VARCHAR(256)",
            "ALTER TABLE tasks ADD COLUMN heartbeat_workflow_name VARCHAR(256)",
            "ALTER TABLE tasks ADD COLUMN dreaming_days INTEGER DEFAULT 14",
            "ALTER TABLE tasks ADD COLUMN dreaming_min_actions INTEGER DEFAULT 5",
            "ALTER TABLE tasks ADD COLUMN dreaming_persona VARCHAR(64)",
        ]:
            try:
                await conn.execute(text(ddl))
            except Exception:
                pass  # column already exists

    # Seed default admin user + initial action memories
    async with AsyncSessionLocal() as db:
        await seed_default_user(db)
        await action_memory_service.seed_default_actions(db)
        await locutus_service.seed_default_data(db)
        await seven_of_nine_service.seed_default_data(db)
        # Seed default personas from .env when the table is empty.
        try:
            from app.personas import service as persona_service
            seeded = await persona_service.seed_default_personas(db)
            if seeded > 0:
                logger.info(f"Seeded {seeded} default personas (Locutus, Seven of Nine)")
        except Exception:
            logger.exception("Failed to seed default personas")
        # Register Seven's peer-sync comparator skills (idempotent).
        try:
            from app.seven_of_nine.sync_agent import seed_sync_skills
            await seed_sync_skills(db)
        except Exception:
            logger.exception("Failed to seed peer-sync skills")
        # Import failed Archon runs from .archon logs (idempotent).
        try:
            from app.second_brain.archon_ingest import ingest_archon_run_failures
            await ingest_archon_run_failures(db)
        except Exception:
            pass  # log ingestion must never block startup

    # Initialize Dreaming tasks in the scheduler (one per persona)
    async def _init_dreaming_tasks():
        """Register one Dreaming consolidation task per configured persona."""
        try:
            from app.task_automation.service import create_task
            from app.task_automation.scheduler import translate_dreaming_config

            # Persona definitions: (config_prefix, persona_key, display_name)
            personas = [
                (
                    "locutus",
                    "locutus",
                    "Locutus",
                    settings.locutus_dreaming_time,
                    settings.locutus_dreaming_frequency,
                    settings.locutus_dreaming_days,
                    settings.locutus_dreaming_min_actions,
                ),
                (
                    "seven",
                    "seven",
                    "Seven of Nine",
                    settings.seven_dreaming_time,
                    settings.seven_dreaming_frequency,
                    settings.seven_dreaming_days,
                    settings.seven_dreaming_min_actions,
                ),
            ]

            async with AsyncSessionLocal() as db:
                for prefix, persona_key, display_name, dream_time, dream_freq, dream_days, dream_min in personas:
                    cron_expr = translate_dreaming_config(dream_time, dream_freq)
                    task_name = f"{display_name} Dreaming Consolidation"

                    # Check if task already exists (idempotent)
                    from sqlalchemy import select
                    from app.task_automation.models import Task
                    existing = await db.execute(
                        select(Task).where(Task.name == task_name, Task.task_type == "dreaming")
                    )
                    if existing.scalar_one_or_none():
                        logger.info(f"Dreaming task '{task_name}' already exists — skipping")
                        continue

                    task = await create_task(
                        db,
                        name=task_name,
                        task_type="dreaming",
                        schedule=cron_expr,
                        description=f"Consolidates ActionMemory entries into long-term knowledge",
                        tags=["dreaming", "self-improvement", "memory-consolidation"],
                        dreaming_days=dream_days,
                        dreaming_min_actions=dream_min,
                        dreaming_persona=persona_key,
                    )
                    logger.info(f"Dreaming task '{task_name}' registered with schedule: {cron_expr}")
        except Exception:
            logger.exception("Failed to initialize dreaming tasks")

    asyncio.create_task(_init_dreaming_tasks())

    # Initialize scheduler
    await init_scheduler()
    await reload_all_tasks()

    # Initialize Discord Bot (Locutus)
    await _init_discord_bot()

    # Initialize the conference-room meeting service (separate surface, reuses
    # the same persona prompts + LM Studio clients). Independent of whether the
    # Discord bots are enabled.
    global _meeting_service
    try:
        _meeting_service = MeetingService()
        await _meeting_service.start()
        set_meeting_service(_meeting_service)
    except Exception:
        logger.exception("Failed to initialize MeetingService")

    yield

    # Shutdown scheduler
    await shutdown_scheduler()
    await engine.dispose()

    # Shutdown Discord Bot
    await _shutdown_discord_bot()

    if _meeting_service:
        await _meeting_service.stop()

    # Flush buffered Langfuse traces (no-op when tracing is disabled)
    from app.shared import tracing
    tracing.shutdown()


app = FastAPI(
    title="BorgOS API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(archon_router)
app.include_router(archon_system_router)
app.include_router(brain_router)
app.include_router(action_router)
app.include_router(insight_router)
app.include_router(task_router)
app.include_router(skills_router)
app.include_router(dreaming_router)
app.include_router(vault_router)
app.include_router(discord_locutus_router)
app.include_router(locutus_router)
app.include_router(seven_of_nine_router)
app.include_router(agent_sandbox_router)
app.include_router(observability_router)
app.include_router(peer_sync_router)
app.include_router(peer_router)
app.include_router(meeting_router)
app.include_router(personas_router)


@app.get("/api/health")
async def health():
    uptime = int(time.time() - START_TIME)
    return {
        "status": "nominal",
        "uptime_seconds": max(1, uptime),
        "modules": {
            "auth": "online",
            "archon_hub": "online",
            "second_brain": "online",
            "task_automation": "online",
            "skills": "online",
            "dreaming": "online",
        },
    }
