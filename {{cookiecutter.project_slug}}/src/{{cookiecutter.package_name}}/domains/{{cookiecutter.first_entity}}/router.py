{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
{% set entity_word = cookiecutter.first_entity | replace('_', ' ') -%}
{% set an = 'an' if entity_word[0] in 'aeiou' else 'a' -%}
"""HTTP routes for the {{ cookiecutter.first_entity }} domain."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from {{ cookiecutter.package_name }}.core.database import SessionDep
{%- if cookiecutter.use_redis == "yes" %}
from {{ cookiecutter.package_name }}.core.idempotency import IdempotentAPIRoute, idempotent
{%- endif %}
from {{ cookiecutter.package_name }}.core.schemas import Page
{%- if cookiecutter.use_auth == "yes" %}
from {{ cookiecutter.package_name }}.domains.auth.dependencies import get_current_active_user
{%- endif %}
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.models import {{ entity_class }}
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.repository import {{ entity_class }}Repository
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.schemas import (
    {{ entity_class }}Create,
    {{ entity_class }}Read,
    {{ entity_class }}Update,
)
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.service import {{ entity_class }}Service


def get_{{ cookiecutter.first_entity }}_service(session: SessionDep) -> {{ entity_class }}Service:
    return {{ entity_class }}Service({{ entity_class }}Repository(session))


ServiceDep = Annotated[{{ entity_class }}Service, Depends(get_{{ cookiecutter.first_entity }}_service)]

router = APIRouter(
    prefix="/{{ cookiecutter.first_entity }}s",
    tags=["{{ cookiecutter.first_entity }}s"],
{%- if cookiecutter.use_auth == "yes" %}
    dependencies=[Depends(get_current_active_user)],
{%- endif %}
{%- if cookiecutter.use_redis == "yes" %}
    route_class=IdempotentAPIRoute,  # activates the @idempotent marker below
{%- endif %}
)


@router.get(
    "",
    response_model=Page[{{ entity_class }}Read],
    summary="List {{ entity_word }}s",
    response_description="One page of {{ entity_word }}s plus the total count.",
)
async def list_{{ cookiecutter.first_entity }}s(
    service: ServiceDep,
    offset: Annotated[int, Query(ge=0, description="Number of records to skip.")] = 0,
    limit: Annotated[int, Query(ge=1, le=200, description="Maximum records to return.")] = 50,
) -> Page[{{ entity_class }}]:
    """List {{ entity_word }}s in stable (primary-key) order with offset/limit pagination."""
    return await service.list(offset=offset, limit=limit)


@router.post(
    "",
    response_model={{ entity_class }}Read,
    status_code=status.HTTP_201_CREATED,
    summary="Create {{ an }} {{ entity_word }}",
    response_description="The stored {{ entity_word }}, including id and timestamps.",
)
{%- if cookiecutter.use_redis == "yes" %}
@idempotent  # honours the Idempotency-Key header (see core/idempotency.py)
{%- endif %}
async def create_{{ cookiecutter.first_entity }}(data: {{ entity_class }}Create, service: ServiceDep) -> {{ entity_class }}:
    """Create {{ an }} {{ entity_word }} from the request body and return the stored record."""
    return await service.create(data)


@router.get(
    "/{entity_id}",
    response_model={{ entity_class }}Read,
    summary="Get {{ an }} {{ entity_word }} by id",
)
async def get_{{ cookiecutter.first_entity }}(entity_id: UUID, service: ServiceDep) -> {{ entity_class }}:
    """Fetch a single {{ entity_word }} by its UUID; responds 404 when it does not exist."""
    return await service.get(entity_id)


@router.patch(
    "/{entity_id}",
    response_model={{ entity_class }}Read,
    summary="Update {{ an }} {{ entity_word }}",
)
async def update_{{ cookiecutter.first_entity }}(entity_id: UUID, data: {{ entity_class }}Update, service: ServiceDep) -> {{ entity_class }}:
    """Apply a partial update; omitted fields keep their current values."""
    return await service.update(entity_id, data)


@router.delete(
    "/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete {{ an }} {{ entity_word }}",
)
async def delete_{{ cookiecutter.first_entity }}(entity_id: UUID, service: ServiceDep) -> None:
    """Delete {{ an }} {{ entity_word }} permanently; responds 404 when it does not exist."""
    await service.delete(entity_id)
