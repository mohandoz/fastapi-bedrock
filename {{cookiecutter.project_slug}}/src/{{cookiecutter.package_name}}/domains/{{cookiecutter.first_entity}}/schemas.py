{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
"""Request and response schemas for the {{ cookiecutter.first_entity }} domain."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.models import {{ entity_class }}Base


class {{ entity_class }}Create({{ entity_class }}Base):
    """Payload for creating a {{ cookiecutter.first_entity }}."""


class {{ entity_class }}Update(SQLModel):
    """Payload for a partial update; omitted fields are left unchanged.

    Constraints mirror ``{{ entity_class }}Base`` so a PATCH cannot smuggle in
    values the create path would reject (or the database would refuse).
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None

    @field_validator("name", "is_active")
    @classmethod
    def _reject_explicit_null(cls, value: str | bool | None) -> str | bool:
        # Only runs when the field is provided; both columns are NOT NULL.
        if value is None:
            msg = "field cannot be null"
            raise ValueError(msg)
        return value


class {{ entity_class }}Read({{ entity_class }}Base):
    """Representation returned by the API."""

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
