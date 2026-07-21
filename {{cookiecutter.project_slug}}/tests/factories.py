{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
"""Polyfactory factories for generating test data."""

from __future__ import annotations

from polyfactory.factories.pydantic_factory import ModelFactory

from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.schemas import {{ entity_class }}Create


class {{ entity_class }}CreateFactory(ModelFactory[{{ entity_class }}Create]):
    __model__ = {{ entity_class }}Create
