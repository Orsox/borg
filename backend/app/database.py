from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _resolve_db_url() -> str:
    url = settings.database_url
    if "sqlite" in url and "///" in url:
        prefix, path_part = url.split("///", 1)
        resolved = str(Path(path_part).expanduser().resolve())
        return f"{prefix}///{resolved}"
    return url


engine = create_async_engine(
    _resolve_db_url(),
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
