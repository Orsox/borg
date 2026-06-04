import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

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
from app.second_brain.router import router as brain_router
from app.second_brain.action_router import router as action_router
from app.second_brain import action_service as action_memory_service
from app.task_automation.models import Task, TaskRun  # noqa: F401
from app.task_automation.router import router as task_router
from app.task_automation.scheduler import init_scheduler, shutdown_scheduler, reload_all_tasks
from app.skills.router import router as skills_router
from app.dreaming.router import router as dreaming_router
from app.auth.service import seed_default_user
from app.config import settings
from app.discord_bot.router import set_bot_service, router as locutus_router
from app.discord_bot.config import BotConfig
from app.discord_bot.service import DiscordBotService
from app.discord_bot.listener import TaskEventListener
from app.discord_bot.bot import BotClient
from app.database import Base, AsyncSessionLocal, engine
from app.shared.exceptions import (
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

START_TIME = time.time()
logger = logging.getLogger(__name__)

# Global references for Discord Bot lifecycle management
_bot_service: DiscordBotService | None = None
_sse_listener: TaskEventListener | None = None
_bot_client: BotClient | None = None
_bot_task: asyncio.Task | None = None


async def _init_discord_bot() -> None:
    """Initialisiere Locutus Discord-Bot."""
    global _bot_service, _sse_listener, _bot_client, _bot_task

    config = BotConfig.from_env()
    errors = config.validate()
    if errors:
        logger.warning(f"Discord Bot config errors: {errors}")
        return

    if not config.enabled:
        logger.info("Discord Bot disabled (DISCORD_BOT_ENABLED=false)")
        return

    try:
        # Service initialisieren
        _bot_service = DiscordBotService(config)
        await _bot_service.start()
        set_bot_service(_bot_service)

        # Bot-Client initialisieren
        _bot_client = BotClient(config=config, service=_bot_service)

        # SSE-Listener initialisieren — sendet Notifications an Discord
        async def notification_callback(content: str) -> None:
            """Callback für Task-Notifications."""
            if _bot_client and _bot_client.is_ready():
                await _bot_client.send_notification(content)
            else:
                logger.info(f"Notification (bot not ready): {content}")

        _sse_listener = TaskEventListener(notification_callback)
        await _sse_listener.start()

        # Bot verbinden
        token = config.token
        if not token:
            logger.warning("DISCORD_BOT_TOKEN is empty — not connecting to Discord")
            return

        logger.info("Starting BotClient...")
        _bot_task = asyncio.create_task(_bot_client.start(token), name="locutus-bot")
        _bot_task.add_done_callback(_log_bot_task_result)
        await _bot_client.wait_until_ready(timeout=30.0)
        logger.info("Discord Bot 'Locutus' initialized")
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


async def _shutdown_discord_bot() -> None:
    """Shutdown Locutus Discord-Bot."""
    global _bot_service, _sse_listener, _bot_client, _bot_task

    if _sse_listener:
        await _sse_listener.stop()
        logger.info("TaskEventListener stopped")

    if _bot_client:
        await _bot_client.close()
        logger.info("BotClient closed")

    if _bot_task and not _bot_task.done():
        _bot_task.cancel()
        try:
            await _bot_task
        except asyncio.CancelledError:
            pass
        logger.info("BotClient task cancelled")

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
        ]:
            try:
                await conn.execute(text(ddl))
            except Exception:
                pass  # column already exists

    # Seed default admin user + initial action memories
    async with AsyncSessionLocal() as db:
        await seed_default_user(db)
        await action_memory_service.seed_default_actions(db)
        # Import failed Archon runs from .archon logs (idempotent).
        try:
            from app.second_brain.archon_ingest import ingest_archon_run_failures
            await ingest_archon_run_failures(db)
        except Exception:
            pass  # log ingestion must never block startup

    # Start Dreaming consolidation on startup (one-shot, non-blocking)
    async def _run_initial_dreaming():
        """Run one Dreaming cycle at startup to consolidate prior memory."""
        try:
            async with AsyncSessionLocal() as db:
                from app.dreaming.service import run_dreaming_cycle
                result = await run_dreaming_cycle(db, days=30, min_actions=3)
                logger.info(f"Initial dreaming cycle: {result.get('status', 'unknown')}")
        except Exception:
            pass  # dreaming must never block startup

    asyncio.create_task(_run_initial_dreaming())

    # Initialize scheduler
    await init_scheduler()
    await reload_all_tasks()

    # Initialize Discord Bot (Locutus)
    await _init_discord_bot()

    yield

    # Shutdown scheduler
    await shutdown_scheduler()
    await engine.dispose()

    # Shutdown Discord Bot
    await _shutdown_discord_bot()


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
app.include_router(task_router)
app.include_router(skills_router)
app.include_router(dreaming_router)
app.include_router(vault_router)
app.include_router(locutus_router)


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
