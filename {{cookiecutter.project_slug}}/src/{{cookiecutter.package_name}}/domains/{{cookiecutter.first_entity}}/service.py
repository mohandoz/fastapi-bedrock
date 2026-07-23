{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
"""Business logic for the {{ cookiecutter.first_entity }} domain."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm.exc import StaleDataError

from {{ cookiecutter.package_name }}.core.exceptions import NotFoundError
from {{ cookiecutter.package_name }}.core.schemas import Page
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.models import {{ entity_class }}
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.repository import {{ entity_class }}Repository
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.schemas import (
    {{ entity_class }}Create,
    {{ entity_class }}Update,
)


class {{ entity_class }}Service:
    """Coordinates {{ cookiecutter.first_entity }} use cases on top of the repository."""

    def __init__(self, repository: {{ entity_class }}Repository) -> None:
        self.repository = repository

    async def get(self, entity_id: UUID) -> {{ entity_class }}:
        obj = await self.repository.get(entity_id)
        if obj is None:
            raise NotFoundError(f"{{ entity_class }} {entity_id} not found")
        return obj

    async def list(self, *, offset: int = 0, limit: int = 100) -> Page[{{ entity_class }}]:
        items = await self.repository.list(offset=offset, limit=limit)
        total = await self.repository.count()
        return Page(items=list(items), total=total, offset=offset, limit=limit)

    async def create(self, data: {{ entity_class }}Create) -> {{ entity_class }}:
        return await self.repository.add({{ entity_class }}(**data.model_dump()))

    async def update(self, entity_id: UUID, data: {{ entity_class }}Update) -> {{ entity_class }}:
        obj = await self.get(entity_id)
        try:
            return await self.repository.update(obj, data.model_dump(exclude_unset=True))
        except StaleDataError as exc:  # row deleted between our SELECT and the UPDATE
            raise NotFoundError(f"{{ entity_class }} {entity_id} not found") from exc

    async def delete(self, entity_id: UUID) -> None:
        obj = await self.get(entity_id)
        await self.repository.delete(obj)
