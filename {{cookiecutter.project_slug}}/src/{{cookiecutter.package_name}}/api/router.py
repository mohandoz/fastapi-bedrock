"""Aggregates every domain router under the versioned API prefix."""

from __future__ import annotations

from fastapi import APIRouter

from {{ cookiecutter.package_name }}.api import health
{%- if cookiecutter.use_auth == "yes" %}
from {{ cookiecutter.package_name }}.domains.auth.router import router as auth_router
{%- endif %}
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.router import (
    router as {{ cookiecutter.first_entity }}_router,
)

api_router = APIRouter()
api_router.include_router(health.router)
{%- if cookiecutter.use_auth == "yes" %}
api_router.include_router(auth_router)
{%- endif %}
api_router.include_router({{ cookiecutter.first_entity }}_router)
