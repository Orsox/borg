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
from app.auth.models import User  # noqa: F401 — ensures model is registered
from app.auth.router import router as auth_router
from app.second_brain.models import Note, NoteLink  # noqa: F401
from app.second_brain.router import router as brain_router
from app.task_automation.models import Task, TaskRun  # noqa: F401
from app.task_automation.router import router as task_router
from app.task_automation.scheduler import init_scheduler, shutdown_scheduler, reload_all_tasks
from app.auth.service import seed_default_user
from app.config import settings
from app.database import Base, AsyncSessionLocal, engine
from app.shared.exceptions import (
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

START_TIME = time.time()


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
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default admin user
    async with AsyncSessionLocal() as db:
        await seed_default_user(db)

    # Initialize scheduler
    await init_scheduler()
    await reload_all_tasks()

    yield

    # Shutdown scheduler
    await shutdown_scheduler()
    await engine.dispose()


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
app.include_router(archon_router)
app.include_router(brain_router)
app.include_router(task_router)


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
        },
    }
