from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings


def _resolve_db_url() -> str:
    url = settings.database_url
    if "sqlite" in url and "///" in url:
        prefix, path_part = url.split("///", 1)
        resolved = str(Path(path_part).expanduser().resolve())
        return f"{prefix}///{resolved}"
    return url


sqlite_connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}
# WAL mode + busy timeout to avoid "database is locked" with concurrent sessions
if "sqlite" in settings.database_url:
    sqlite_connect_args["timeout"] = 30  # seconds to wait for lock

engine = create_async_engine(
    _resolve_db_url(),
    echo=False,
    connect_args=sqlite_connect_args,
    poolclass=NullPool,  # aiosqlite: one connection at a time, no pooling
)

# Enable WAL mode for better concurrency with SQLite + aiosqlite
if "sqlite" in settings.database_url:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
