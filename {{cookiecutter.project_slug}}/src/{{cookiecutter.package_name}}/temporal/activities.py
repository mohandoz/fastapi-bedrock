{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
"""Temporal activities for the {{ cookiecutter.first_entity }} domain.

Activities perform the I/O. Each opens its own async DB session and must be
idempotent, because Temporal may retry it.
"""

from __future__ import annotations

from uuid import UUID

from temporalio import activity

from {{ cookiecutter.package_name }}.core.database import async_session_factory
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.repository import {{ entity_class }}Repository


@activity.defn
async def process_{{ cookiecutter.first_entity }}_activity(entity_id: str) -> str:
    """Load a {{ cookiecutter.first_entity }} and process it. Safe to retry."""
    activity.logger.info(
        "processing {{ cookiecutter.first_entity }} %s (attempt %s)",
        entity_id,
        activity.info().attempt,
    )
    async with async_session_factory() as session:
        try:
            repository = {{ entity_class }}Repository(session)
            obj = await repository.get(UUID(entity_id))
            if obj is None:
                return f"{{ cookiecutter.first_entity }} {entity_id} not found"
            # Real side effects (call an API, transform data, ...) go here.
            await session.commit()
            return f"processed {{ cookiecutter.first_entity }} {entity_id}"
        except Exception:
            await session.rollback()
            raise
