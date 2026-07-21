"""Shared pytest fixtures for the test suite."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import get_session
from {{ cookiecutter.package_name }}.main import create_app

API = settings.api_v1_prefix
TEST_DATABASE_URL = "sqlite+aiosqlite://"


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as db_session:
        yield db_session


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as db_session:
            try:
                yield db_session
                await db_session.commit()
            except Exception:
                await db_session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.clear()

{% if cookiecutter.use_auth == "yes" %}
@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    credentials = {"email": "fixture-user@example.com", "password": "supersecret123"}
    await client.post(f"{API}/auth/register", json=credentials)
    response = await client.post(
        f"{API}/auth/login",
        data={"username": credentials["email"], "password": credentials["password"]},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
{% else %}
@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {}
{% endif %}
