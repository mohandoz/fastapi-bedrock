{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
"""Request and response schemas for the {{ cookiecutter.first_entity }} domain."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlmodel import SQLModel

from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.models import {{ entity_class }}Base


class {{ entity_class }}Create({{ entity_class }}Base):
    """Payload for creating a {{ cookiecutter.first_entity }}."""


class {{ entity_class }}Update(SQLModel):
    """Payload for a partial update; every field is optional."""

    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class {{ entity_class }}Read({{ entity_class }}Base):
    """Representation returned by the API."""

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
