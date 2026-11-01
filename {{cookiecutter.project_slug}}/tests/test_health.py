"""Tests for the health and readiness probes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

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


async def test_ready_maps_dependency_failure_to_503(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(*_args: object, **_kwargs: object) -> None:
        raise ConnectionError("database unavailable")

    monkeypatch.setattr(AsyncSession, "exec", fail)
    response = await client.get(f"{API}/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "Dependency check failed."
