import os
import sys
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = str(Path(__file__).resolve().parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Tests run as development unless a test overrides settings explicitly (config now fails closed)
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEV_AUTH_BYPASS", "true")
# Never call the real Gemini API from tests, even if backend/.env holds a key; tests inject mocked clients
os.environ["GEMINI_API_KEY"] = ""
# Fast background-removal model for the real-worker integration test (production default is birefnet-general)
os.environ.setdefault("REMBG_MODEL", "u2net")

import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app as fastapi_app
from app.db.base import Base
import app.models
from app.db.session import get_db
from app.core.config import settings

# Shared-cache in-memory SQLite database
TEST_DATABASE_URL = "sqlite+aiosqlite:///file:aura_mem?mode=memory&cache=shared&uri=true"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False, "uri": True},
    poolclass=StaticPool,
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession, monkeypatch) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db

    import app.db.session as session_module
    import app.workers.arq_worker as arq_module
    monkeypatch.setattr(session_module, "AsyncSessionLocal", TestingSessionLocal)
    monkeypatch.setattr(arq_module, "AsyncSessionLocal", TestingSessionLocal)

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    fastapi_app.dependency_overrides.clear()
