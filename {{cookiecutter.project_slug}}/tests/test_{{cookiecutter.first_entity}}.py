{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
"""Tests for the {{ cookiecutter.first_entity }} CRUD endpoints."""

from __future__ import annotations

from httpx import AsyncClient

from {{ cookiecutter.package_name }}.core.config import settings
from tests.factories import {{ entity_class }}CreateFactory

API = settings.api_v1_prefix
BASE = f"{API}/{{ cookiecutter.first_entity }}s"


async def test_create_and_read(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    payload = {{ entity_class }}CreateFactory.build().model_dump()
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
        payload = {{ entity_class }}CreateFactory.build().model_dump()
        await client.post(BASE, json=payload, headers=auth_headers)
    response = await client.get(BASE, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 3
    assert len(body["items"]) >= 3


async def test_update(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    payload = {{ entity_class }}CreateFactory.build().model_dump()
    created = (await client.post(BASE, json=payload, headers=auth_headers)).json()
    updated = await client.patch(
        f"{BASE}/{created['id']}",
        json={"name": "updated-name"},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "updated-name"


async def test_delete(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    payload = {{ entity_class }}CreateFactory.build().model_dump()
    created = (await client.post(BASE, json=payload, headers=auth_headers)).json()
    deleted = await client.delete(f"{BASE}/{created['id']}", headers=auth_headers)
    assert deleted.status_code == 204
    missing = await client.get(f"{BASE}/{created['id']}", headers=auth_headers)
    assert missing.status_code == 404


async def test_get_unknown_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    unknown = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"{BASE}/{unknown}", headers=auth_headers)
    assert response.status_code == 404
