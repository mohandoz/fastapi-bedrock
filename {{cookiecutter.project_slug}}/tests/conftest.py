"""Shared pytest fixtures for the test suite (Postgres via testcontainers)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
{%- if cookiecutter.use_redis == "yes" %}
import redis.asyncio as aioredis
{%- endif %}
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from testcontainers.postgres import PostgresContainer
{%- if cookiecutter.use_redis == "yes" %}
from testcontainers.redis import RedisContainer
{%- endif %}

# --- Hermetic test environment ---------------------------------------------
# Pin every setting that can change test behavior BEFORE the settings singleton
# is imported. Plain assignment beats both exported shell variables and a local
# .env file (pydantic-settings reads .env only for keys absent from the
# environment), so nothing on the developer's machine leaks into the suite.
os.environ["ENVIRONMENT"] = "local"
os.environ["DEBUG"] = "false"
os.environ["ALLOWED_HOSTS"] = "*"  # comma-separated format, same as .env.example
os.environ["DATABASE_URL"] = (  # never connected to; fixtures use the container URL
    "postgresql+asyncpg://postgres:postgres@localhost:5432/{{ cookiecutter.package_name }}"
)
{%- if cookiecutter.use_auth == "yes" %}
os.environ["SECRET_KEY"] = "test-only-secret-key-not-for-production-use"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "7"
{%- endif %}
{%- if cookiecutter.use_rate_limiting == "yes" %}
os.environ["RATE_LIMIT"] = "100/minute"
{%- endif %}
{%- if cookiecutter.use_sentry == "yes" %}
os.environ["SENTRY_DSN"] = ""  # falsy -> Sentry stays disabled under test
{%- endif %}
{%- if cookiecutter.use_redis == "yes" %}
os.environ["REDIS_URL"] = "redis://localhost:6379/0"  # fixtures use the container URL
os.environ["CACHE_DEFAULT_TTL"] = "300"
{%- endif %}
{%- if cookiecutter.use_observability == "yes" %}
os.environ["OTEL_ENABLED"] = "false"
{%- endif %}
{%- if cookiecutter.use_http_client == "yes" %}
os.environ["HTTP_TIMEOUT"] = "10.0"
os.environ["HTTP_RETRIES"] = "3"
os.environ["HTTP_BREAKER_FAILURE_THRESHOLD"] = "5"
os.environ["HTTP_BREAKER_RESET_TIMEOUT"] = "30.0"
{%- endif %}

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import get_session
{%- if cookiecutter.use_redis == "yes" %}

# Imported for its side effect: registers the outbox table on SQLModel.metadata.
from {{ cookiecutter.package_name }}.events import models as _event_models  # noqa: F401
{%- endif %}
from {{ cookiecutter.package_name }}.main import create_app

API = settings.api_v1_prefix


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Start one throwaway PostgreSQL container for the whole test session."""
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as container:
        yield str(container.get_connection_url())


@pytest_asyncio.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(database_url)
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    # Isolate tests: wipe every table after each one.
    async with eng.begin() as conn:
        for table in reversed(SQLModel.metadata.sorted_tables):
            await conn.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))
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
{%- if cookiecutter.use_redis == "yes" %}
    redis_url: str,
{%- endif %}
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
{%- if cookiecutter.use_rate_limiting == "yes" %}
    # slowapi checks `app.state.limiter.enabled` per request; disable it so
    # fixtures hitting strictly limited routes (e.g. /auth/register) never 429.
    app.state.limiter.enabled = False
{%- endif %}
    app.dependency_overrides[get_session] = override_get_session
{%- if cookiecutter.use_redis == "yes" %}
    # The lifespan is not run under ASGITransport, so seed the resources it builds.
    app.state.redis = aioredis.from_url(redis_url, decode_responses=True)
{%- endif %}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
{%- if cookiecutter.use_redis == "yes" %}
    await app.state.redis.aclose()
{%- endif %}
    app.dependency_overrides.clear()
{%- if cookiecutter.use_redis == "yes" %}


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:8-alpine") as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncIterator[aioredis.Redis]:
    client = aioredis.from_url(redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.aclose()
{%- endif %}
{%- if cookiecutter.use_auth == "yes" %}


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
{%- else %}


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {}
{%- endif %}
