{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
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


@router.get("", response_model=Page[{{ entity_class }}Read])
async def list_{{ cookiecutter.first_entity }}s(
    service: ServiceDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[{{ entity_class }}]:
    return await service.list(offset=offset, limit=limit)


@router.post("", response_model={{ entity_class }}Read, status_code=status.HTTP_201_CREATED)
{%- if cookiecutter.use_redis == "yes" %}
@idempotent  # honours the Idempotency-Key header (see core/idempotency.py)
{%- endif %}
async def create_{{ cookiecutter.first_entity }}(
    data: {{ entity_class }}Create, service: ServiceDep
) -> {{ entity_class }}:
    return await service.create(data)


@router.get("/{entity_id}", response_model={{ entity_class }}Read)
async def get_{{ cookiecutter.first_entity }}(entity_id: UUID, service: ServiceDep) -> {{ entity_class }}:
    return await service.get(entity_id)


@router.patch("/{entity_id}", response_model={{ entity_class }}Read)
async def update_{{ cookiecutter.first_entity }}(
    entity_id: UUID, data: {{ entity_class }}Update, service: ServiceDep
) -> {{ entity_class }}:
    return await service.update(entity_id, data)


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_{{ cookiecutter.first_entity }}(entity_id: UUID, service: ServiceDep) -> None:
    await service.delete(entity_id)
