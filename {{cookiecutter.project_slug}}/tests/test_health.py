"""Tests for the health and readiness probes."""

from __future__ import annotations

from httpx import AsyncClient

from {{ cookiecutter.package_name }}.core.config import settings

API = settings.api_v1_prefix


async def test_health(client: AsyncClient) -> None:
    response = await client.get(f"{API}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready(client: AsyncClient) -> None:
    response = await client.get(f"{API}/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
