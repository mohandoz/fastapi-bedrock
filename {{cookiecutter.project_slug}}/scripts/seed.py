{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
"""Seed the local database with demo data.

Idempotent: exits without writing when the table already contains rows.
Refuses to run outside the local environment.

Usage:
    make seed
    uv run python scripts/seed.py --count 50
"""

from __future__ import annotations

import argparse
import asyncio

from polyfactory.factories.pydantic_factory import ModelFactory

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import async_session_factory, dispose_db, init_db
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.models import {{ entity_class }}
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.repository import (
    {{ entity_class }}Repository,
)
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.schemas import {{ entity_class }}Create


class {{ entity_class }}CreateFactory(ModelFactory[{{ entity_class }}Create]):
    """Generates valid ``{{ entity_class }}Create`` payloads."""

    __model__ = {{ entity_class }}Create


async def seed(count: int) -> None:
    """Insert ``count`` generated {{ cookiecutter.first_entity }}s unless the table already has data."""
    async with async_session_factory() as session:
        repository = {{ entity_class }}Repository(session)
        existing = await repository.count()
        if existing:
            print(f"'{{ cookiecutter.first_entity }}s' already has {existing} rows - nothing to do.")
            return
        for payload in {{ entity_class }}CreateFactory.batch(size=count):
            await repository.add({{ entity_class }}(**payload.model_dump()))
        await session.commit()
        print(f"Seeded {count} rows into '{{ cookiecutter.first_entity }}s'.")


async def main(count: int) -> None:
    if not settings.is_local:
        msg = "Refusing to seed: ENVIRONMENT is not 'local'."
        raise SystemExit(msg)
    # Local convenience: creates missing tables when DB_AUTO_CREATE allows it.
    await init_db()
    try:
        await seed(count)
    finally:
        await dispose_db()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the local database with demo data.")
    parser.add_argument(
        "--count", type=int, default=25, help="rows to create (default: %(default)s)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args().count))
