"""Test configuration for BorgOS backend."""

import pytest
import pytest_asyncio

from app.auth.service import seed_default_user
from app.database import Base, AsyncSessionLocal, engine
from app.archon_system.models import ArchonSystemHealth, ArchonRun, ArchonCodebase, ArchonWorkflowMeta  # noqa: F401
from app.second_brain.action_models import ActionMemory  # noqa: F401


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables and seed default user before each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        await seed_default_user(db)

    yield

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
