{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
"""Repository for the {{ cookiecutter.first_entity }} domain."""

from __future__ import annotations

from sqlmodel import select

from {{ cookiecutter.package_name }}.core.repository import BaseRepository
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.models import {{ entity_class }}


class {{ entity_class }}Repository(BaseRepository[{{ entity_class }}]):
    model = {{ entity_class }}

    async def get_by_name(self, name: str) -> {{ entity_class }} | None:
        result = await self.session.exec(select({{ entity_class }}).where({{ entity_class }}.name == name))
        return result.first()
