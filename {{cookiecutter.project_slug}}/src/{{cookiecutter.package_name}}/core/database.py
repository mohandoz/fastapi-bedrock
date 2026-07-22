"""Async database engine, session factory and the FastAPI session dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from {{ cookiecutter.package_name }}.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a session that commits on success and rolls back on error."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _import_models() -> None:
    """Import model modules so their tables register on ``SQLModel.metadata``."""
    from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }} import models  # noqa: F401
{%- if cookiecutter.use_auth == "yes" %}
    from {{ cookiecutter.package_name }}.domains.auth import models as auth_models  # noqa: F401
{%- endif %}
{%- if cookiecutter.use_redis == "yes" %}
    from {{ cookiecutter.package_name }}.events import models as event_models  # noqa: F401
{%- endif %}


async def init_db() -> None:
    """Create all tables (used locally and in tests; production uses Alembic)."""
    _import_models()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def dispose_db() -> None:
    await engine.dispose()
