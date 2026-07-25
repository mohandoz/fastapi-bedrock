"""Scaffold a new domain: models, schemas, repository, service, router and tests.

Usage:
    make new-domain name=order
    uv run python scripts/new_domain.py order

Creates ``src/{{ cookiecutter.package_name }}/domains/<name>/`` mirroring the
``{{ cookiecutter.first_entity }}`` slice plus ``tests/test_<name>.py``, then
prints the registration lines (API router, model imports) to add by hand.
"""

from __future__ import annotations

import argparse
import keyword
import re
from pathlib import Path
from string import Template

PACKAGE = "{{ cookiecutter.package_name }}"
ROOT = Path(__file__).resolve().parents[1]
DOMAINS_DIR = ROOT / "src" / PACKAGE / "domains"
TESTS_DIR = ROOT / "tests"

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

INIT_TEMPLATE = Template('"""The $name domain."""\n')

MODELS_TEMPLATE = Template('''"""Database models for the $name domain."""

from __future__ import annotations

from sqlmodel import Field, SQLModel

from $package.core.models import TimestampMixin, UUIDMixin


class ${entity}Base(SQLModel):
    """Fields shared by the table model and the write schemas."""

    name: str = Field(index=True, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = Field(default=True)


class $entity(${entity}Base, UUIDMixin, TimestampMixin, table=True):
    __tablename__ = "${name}s"
''')

SCHEMAS_TEMPLATE = Template('''"""Request and response schemas for the $name domain."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from $package.domains.$name.models import ${entity}Base


class ${entity}Create(${entity}Base):
    """Payload for creating a $name."""


class ${entity}Update(SQLModel):
    """Payload for a partial update; omitted fields are left unchanged.

    Constraints mirror ``${entity}Base`` so a PATCH cannot smuggle in
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


class ${entity}Read(${entity}Base):
    """Representation returned by the API."""

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
''')

REPOSITORY_TEMPLATE = Template('''"""Repository for the $name domain."""

from __future__ import annotations

from sqlmodel import select

from $package.core.repository import BaseRepository
from $package.domains.$name.models import $entity


class ${entity}Repository(BaseRepository[$entity]):
    model = $entity

    async def get_by_name(self, name: str) -> $entity | None:
        result = await self.session.exec(select($entity).where($entity.name == name))
        return result.first()
''')

SERVICE_TEMPLATE = Template('''"""Business logic for the $name domain."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm.exc import StaleDataError

from $package.core.exceptions import NotFoundError
from $package.core.schemas import Page
from $package.domains.$name.models import $entity
from $package.domains.$name.repository import ${entity}Repository
from $package.domains.$name.schemas import (
    ${entity}Create,
    ${entity}Update,
)


class ${entity}Service:
    """Coordinates $name use cases on top of the repository."""

    def __init__(self, repository: ${entity}Repository) -> None:
        self.repository = repository

    async def get(self, entity_id: UUID) -> $entity:
        obj = await self.repository.get(entity_id)
        if obj is None:
            raise NotFoundError(f"$entity {entity_id} not found")
        return obj

    async def list(self, *, offset: int = 0, limit: int = 100) -> Page[$entity]:
        items = await self.repository.list(offset=offset, limit=limit)
        total = await self.repository.count()
        return Page(items=list(items), total=total, offset=offset, limit=limit)

    async def create(self, data: ${entity}Create) -> $entity:
        return await self.repository.add($entity(**data.model_dump()))

    async def update(self, entity_id: UUID, data: ${entity}Update) -> $entity:
        obj = await self.get(entity_id)
        try:
            return await self.repository.update(obj, data.model_dump(exclude_unset=True))
        except StaleDataError as exc:  # row deleted between our SELECT and the UPDATE
            raise NotFoundError(f"$entity {entity_id} not found") from exc

    async def delete(self, entity_id: UUID) -> None:
        obj = await self.get(entity_id)
        await self.repository.delete(obj)
''')

ROUTER_TEMPLATE = Template('''"""HTTP routes for the $name domain."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from $package.core.database import SessionDep
from $package.core.schemas import Page
{%- if cookiecutter.use_auth == "yes" %}
from $package.domains.auth.dependencies import get_current_active_user
{%- endif %}
from $package.domains.$name.models import $entity
from $package.domains.$name.repository import ${entity}Repository
from $package.domains.$name.schemas import (
    ${entity}Create,
    ${entity}Read,
    ${entity}Update,
)
from $package.domains.$name.service import ${entity}Service


def get_${name}_service(session: SessionDep) -> ${entity}Service:
    return ${entity}Service(${entity}Repository(session))


ServiceDep = Annotated[${entity}Service, Depends(get_${name}_service)]

router = APIRouter(
    prefix="/${name}s",
    tags=["${name}s"],
{%- if cookiecutter.use_auth == "yes" %}
    dependencies=[Depends(get_current_active_user)],
{%- endif %}
)


@router.get("", response_model=Page[${entity}Read])
async def list_${name}s(
    service: ServiceDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[$entity]:
    return await service.list(offset=offset, limit=limit)


@router.post("", response_model=${entity}Read, status_code=status.HTTP_201_CREATED)
async def create_${name}(data: ${entity}Create, service: ServiceDep) -> $entity:
    return await service.create(data)


@router.get("/{entity_id}", response_model=${entity}Read)
async def get_${name}(entity_id: UUID, service: ServiceDep) -> $entity:
    return await service.get(entity_id)


@router.patch("/{entity_id}", response_model=${entity}Read)
async def update_${name}(
    entity_id: UUID,
    data: ${entity}Update,
    service: ServiceDep,
) -> $entity:
    return await service.update(entity_id, data)


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_${name}(entity_id: UUID, service: ServiceDep) -> None:
    await service.delete(entity_id)
''')

TEST_TEMPLATE = Template('''"""Tests for the $name CRUD endpoints."""

from __future__ import annotations

from httpx import AsyncClient
from polyfactory.factories.pydantic_factory import ModelFactory

from $package.core.config import settings
from $package.domains.$name.schemas import ${entity}Create

API = settings.api_v1_prefix
BASE = f"{API}/${name}s"


class ${entity}CreateFactory(ModelFactory[${entity}Create]):
    __model__ = ${entity}Create


async def test_create_and_read(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    payload = ${entity}CreateFactory.build().model_dump()
    created = await client.post(BASE, json=payload, headers=auth_headers)
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == payload["name"]

    entity_id = body["id"]
    fetched = await client.get(f"{BASE}/{entity_id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == entity_id


async def test_list(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    for _ in range(3):
        payload = ${entity}CreateFactory.build().model_dump()
        await client.post(BASE, json=payload, headers=auth_headers)
    response = await client.get(BASE, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 3
    assert len(body["items"]) >= 3


async def test_update(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    payload = ${entity}CreateFactory.build().model_dump()
    created = (await client.post(BASE, json=payload, headers=auth_headers)).json()
    updated = await client.patch(
        f"{BASE}/{created['id']}",
        json={"name": "updated-name"},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "updated-name"


async def test_delete(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    payload = ${entity}CreateFactory.build().model_dump()
    created = (await client.post(BASE, json=payload, headers=auth_headers)).json()
    deleted = await client.delete(f"{BASE}/{created['id']}", headers=auth_headers)
    assert deleted.status_code == 204
    missing = await client.get(f"{BASE}/{created['id']}", headers=auth_headers)
    assert missing.status_code == 404


async def test_get_unknown_returns_404(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    unknown = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"{BASE}/{unknown}", headers=auth_headers)
    assert response.status_code == 404
''')

DOMAIN_FILES: dict[str, Template] = {
    "__init__.py": INIT_TEMPLATE,
    "models.py": MODELS_TEMPLATE,
    "schemas.py": SCHEMAS_TEMPLATE,
    "repository.py": REPOSITORY_TEMPLATE,
    "service.py": SERVICE_TEMPLATE,
    "router.py": ROUTER_TEMPLATE,
}


def class_name(name: str) -> str:
    """``order_line`` -> ``OrderLine`` (the rule the template itself uses)."""
    return name.replace("_", " ").title().replace(" ", "")


def validate(name: str) -> str | None:
    """Return an error message when ``name`` cannot become a domain, else ``None``."""
    if NAME_RE.match(name) is None:
        return f"invalid name {name!r}: use lowercase snake_case, e.g. 'order' or 'order_line'"
    if keyword.iskeyword(name):
        return f"invalid name {name!r}: it is a Python keyword"
    if (DOMAINS_DIR / name).exists():
        return f"domain {name!r} already exists under src/{PACKAGE}/domains/"
    if (TESTS_DIR / f"test_{name}.py").exists():
        return f"tests/test_{name}.py already exists"
    return None


def scaffold(name: str) -> list[Path]:
    """Write the domain files and the test module; return the created paths."""
    mapping = {"package": PACKAGE, "name": name, "entity": class_name(name)}
    domain_dir = DOMAINS_DIR / name
    domain_dir.mkdir()
    created: list[Path] = []
    for filename, template in DOMAIN_FILES.items():
        path = domain_dir / filename
        path.write_text(template.substitute(mapping), encoding="utf-8")
        created.append(path)
    test_path = TESTS_DIR / f"test_{name}.py"
    test_path.write_text(TEST_TEMPLATE.substitute(mapping), encoding="utf-8")
    created.append(test_path)
    return created


def print_next_steps(name: str) -> None:
    model_import = f"from {PACKAGE}.domains.{name} import models as {name}_models  # noqa: F401"
    print(
        f"""
Wire the new domain up (three one-line edits):

1. src/{PACKAGE}/api/router.py
       from {PACKAGE}.domains.{name}.router import router as {name}_router
       api_router.include_router({name}_router)

2. src/{PACKAGE}/core/database.py — inside _import_models():
       {model_import}

3. migrations/env.py — next to the other model imports:
       {model_import}

Then:
    make format
    make revision m="create {name}s table"
    make migrate
    make test
"""
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a new domain vertical slice.")
    parser.add_argument("name", help="domain name in lowercase snake_case, e.g. 'order'")
    args = parser.parse_args()
    name: str = args.name
    error = validate(name)
    if error is not None:
        parser.error(error)
    for path in scaffold(name):
        print(f"created {path.relative_to(ROOT)}")
    print_next_steps(name)


if __name__ == "__main__":
    main()
