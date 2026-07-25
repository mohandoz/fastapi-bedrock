{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
"""Tests for Idempotency-Key replay semantics (core/idempotency.py)."""

from __future__ import annotations

import json
import uuid

import redis.asyncio as redis
from httpx import AsyncClient

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.idempotency import (
    IDEMPOTENCY_KEY_HEADER,
    REPLAYED_HEADER,
)
from tests.factories import {{ entity_class }}CreateFactory

API = settings.api_v1_prefix
BASE = f"{API}/{{ cookiecutter.first_entity }}s"


def _headers(auth_headers: dict[str, str], key: str) -> dict[str, str]:
    return {**auth_headers, IDEMPOTENCY_KEY_HEADER: key}


async def test_same_key_replays_the_first_response(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = {{ entity_class }}CreateFactory.build().model_dump()
    key = uuid.uuid4().hex

    first = await client.post(BASE, json=payload, headers=_headers(auth_headers, key))
    assert first.status_code == 201
    assert REPLAYED_HEADER not in first.headers

    second = await client.post(BASE, json=payload, headers=_headers(auth_headers, key))
    assert second.status_code == 201
    assert second.headers[REPLAYED_HEADER] == "true"
    assert second.json() == first.json()  # byte-identical replay, same id

    listing = await client.get(BASE, headers=auth_headers)
    assert listing.json()["total"] == 1  # no duplicate row was created


async def test_key_reuse_with_different_body_is_422(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    key = uuid.uuid4().hex
    payload = {{ entity_class }}CreateFactory.build().model_dump()
    first = await client.post(BASE, json=payload, headers=_headers(auth_headers, key))
    assert first.status_code == 201

    payload["name"] = f"{payload['name']}-changed"
    second = await client.post(BASE, json=payload, headers=_headers(auth_headers, key))
    assert second.status_code == 422
    assert second.json()["type"] == "urn:problem-type:idempotency-mismatch"


async def test_concurrent_in_flight_is_409(
    client: AsyncClient, auth_headers: dict[str, str], redis_client: redis.Redis
) -> None:
    key = uuid.uuid4().hex
    # Plant a live claim, as the route class would while a request is in flight.
    await redis_client.set(
        f"idem:POST:{BASE}:{key}",
        json.dumps({"state": "in_flight", "fingerprint": "another-request"}),
        ex=30,
    )
    payload = {{ entity_class }}CreateFactory.build().model_dump()
    response = await client.post(BASE, json=payload, headers=_headers(auth_headers, key))
    assert response.status_code == 409
    assert response.json()["type"] == "urn:problem-type:idempotency-in-flight"


async def test_invalid_key_is_400(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    payload = {{ entity_class }}CreateFactory.build().model_dump()
    response = await client.post(BASE, json=payload, headers=_headers(auth_headers, "x" * 300))
    assert response.status_code == 400
    assert response.json()["type"] == "urn:problem-type:idempotency-invalid-key"


async def test_without_header_requests_are_independent(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = {{ entity_class }}CreateFactory.build().model_dump()
    first = await client.post(BASE, json=payload, headers=auth_headers)
    second = await client.post(BASE, json=payload, headers=auth_headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


async def test_error_responses_release_the_claim(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    key = uuid.uuid4().hex
    invalid = await client.post(BASE, json={"name": ""}, headers=_headers(auth_headers, key))
    assert invalid.status_code == 422  # validation error, not snapshotted

    payload = {{ entity_class }}CreateFactory.build().model_dump()
    retry = await client.post(BASE, json=payload, headers=_headers(auth_headers, key))
    assert retry.status_code == 201  # the failed attempt did not burn the key
