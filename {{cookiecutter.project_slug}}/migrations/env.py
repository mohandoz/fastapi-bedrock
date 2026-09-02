"""Alembic environment, configured for async SQLModel migrations."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

# Import model modules so their tables register on SQLModel.metadata.
# core.models must come first: it sets the constraint naming convention.
from {{ cookiecutter.package_name }}.core import models as core_models  # noqa: F401
from {{ cookiecutter.package_name }}.core.config import settings
{%- if cookiecutter.use_auth == "yes" %}
from {{ cookiecutter.package_name }}.domains.auth import models as auth_models  # noqa: F401
{%- endif %}
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }} import models  # noqa: F401
{%- if cookiecutter.use_redis == "yes" %}
from {{ cookiecutter.package_name }}.events import models as event_models  # noqa: F401
{%- endif %}

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata
DATABASE_URL = settings.database_url


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(DATABASE_URL)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
