{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
"""Database models for the {{ cookiecutter.first_entity }} domain."""

from __future__ import annotations

from sqlmodel import Field, SQLModel

from {{ cookiecutter.package_name }}.core.models import TimestampMixin, UUIDMixin


class {{ entity_class }}Base(SQLModel):
    """Fields shared by the table model and the write schemas."""

    name: str = Field(index=True, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = Field(default=True)


class {{ entity_class }}({{ entity_class }}Base, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "{{ cookiecutter.first_entity }}s"
