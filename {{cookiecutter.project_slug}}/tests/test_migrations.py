"""Prove Alembic can build and remove a schema that matches the models."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

from {{ cookiecutter.package_name }}.core.config import settings


async def test_migration_round_trip_matches_metadata(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Upgrade a fresh database, reject model drift, then downgrade cleanly."""
    database_name = f"migration_{uuid.uuid4().hex}"
    source_url = make_url(database_url)
    admin_url = source_url.set(database="postgres")
    target_url = source_url.set(database=database_name)
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")

    async with admin_engine.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{database_name}"'))

    target_url_string = target_url.render_as_string(hide_password=False)
    monkeypatch.setattr(settings, "database_url", target_url_string)

    def migrate() -> None:
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        command.check(config)
        command.downgrade(config, "base")

    try:
        await asyncio.to_thread(migrate)
        target_engine = create_async_engine(target_url)
        try:
            async with target_engine.connect() as connection:
                remaining = set(
                    await connection.run_sync(lambda sync: inspect(sync).get_table_names())
                )
            application_tables = {table.name for table in SQLModel.metadata.sorted_tables}
            assert remaining.isdisjoint(application_tables)
        finally:
            await target_engine.dispose()
    finally:
        async with admin_engine.connect() as connection:
            await connection.execute(
                text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
            )
        await admin_engine.dispose()
