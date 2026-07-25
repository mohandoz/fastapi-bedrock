{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
{% set an = 'an' if cookiecutter.first_entity[0] in 'aeiou' else 'a' -%}
"""MCP server exposing the {{ cookiecutter.first_entity }} domain to AI agents (FastMCP v3).

Tools here are hand-written over the service layer on purpose: a few curated,
well-described tools with tight input schemas are far more reliable for LLM
callers than auto-converting every route. If you want a quick bootstrap of the
whole API instead, ``FastMCP.from_fastapi(app)`` exists — treat it as a
starting point, then replace it with curated tools like the ones below.

The ASGI app from :func:`create_mcp_app` is mounted at ``/mcp`` by
``main.create_app`` (streamable HTTP transport).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.http import StarletteWithLifespan
from pydantic import Field

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import async_session_factory
from {{ cookiecutter.package_name }}.core.exceptions import NotFoundError
from {{ cookiecutter.package_name }}.core.schemas import Page
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.repository import {{ entity_class }}Repository
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.schemas import (
    {{ entity_class }}Create,
    {{ entity_class }}Read,
)
from {{ cookiecutter.package_name }}.domains.{{ cookiecutter.first_entity }}.service import {{ entity_class }}Service
{%- if cookiecutter.use_auth == "yes" %}
from {{ cookiecutter.package_name }}.mcp.auth import build_token_verifier
{%- endif %}

mcp = FastMCP(
    name=settings.project_name,
    instructions=(
        "Curated tools for the {{ cookiecutter.first_entity }} domain of "
        f"{settings.project_name}. Use list/get for lookups and create to add "
        "records; results mirror the REST API at "
        f"{settings.api_v1_prefix}/{{ cookiecutter.first_entity }}s."
    ),
{%- if cookiecutter.use_auth == "yes" %}
    auth=build_token_verifier(),
{%- endif %}
)


@asynccontextmanager
async def _service() -> AsyncIterator[{{ entity_class }}Service]:
    """Yield a service on a fresh session: commit on success, roll back on error.

    MCP requests run outside FastAPI's dependency injection, so this mirrors
    ``core.database.get_session`` semantics by hand.
    """
    async with async_session_factory() as session:
        try:
            yield {{ entity_class }}Service({{ entity_class }}Repository(session))
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@mcp.tool
async def list_{{ cookiecutter.first_entity }}s(
    offset: Annotated[int, Field(ge=0, description="Number of records to skip.")] = 0,
    limit: Annotated[int, Field(ge=1, le=200, description="Maximum records to return.")] = 50,
) -> Page[{{ entity_class }}Read]:
    """List {{ cookiecutter.first_entity }}s in stable (primary-key) order with offset/limit pagination."""
    async with _service() as service:
        page = await service.list(offset=offset, limit=limit)
        return Page[{{ entity_class }}Read](
            items=[{{ entity_class }}Read.model_validate(obj) for obj in page.items],
            total=page.total,
            offset=page.offset,
            limit=page.limit,
        )


@mcp.tool
async def get_{{ cookiecutter.first_entity }}(
    {{ cookiecutter.first_entity }}_id: Annotated[UUID, Field(description="Primary key (UUID) of the {{ cookiecutter.first_entity }}.")],
) -> {{ entity_class }}Read:
    """Fetch a single {{ cookiecutter.first_entity }} by its UUID."""
    async with _service() as service:
        try:
            obj = await service.get({{ cookiecutter.first_entity }}_id)
        except NotFoundError as exc:
            raise ToolError(str(exc)) from exc
        return {{ entity_class }}Read.model_validate(obj)


@mcp.tool
async def create_{{ cookiecutter.first_entity }}(
    name: Annotated[
        str,
        Field(min_length=1, max_length=255, description="Display name; must not be empty."),
    ],
    description: Annotated[
        str | None,
        Field(max_length=2000, description="Optional free-text description."),
    ] = None,
) -> {{ entity_class }}Read:
    """Create {{ an }} {{ cookiecutter.first_entity }} and return the stored record (id and timestamps included)."""
    async with _service() as service:
        obj = await service.create({{ entity_class }}Create(name=name, description=description))
        return {{ entity_class }}Read.model_validate(obj)


def create_mcp_app() -> StarletteWithLifespan:
    """Build the streamable-HTTP ASGI app served at ``/mcp``.

    ``main.create_app`` mounts it and combines ``.lifespan`` with the app
    lifespan so the MCP session manager starts and stops with the service.
    """
    # path="/" because the mount point supplies the /mcp prefix.
    return mcp.http_app(path="/")
