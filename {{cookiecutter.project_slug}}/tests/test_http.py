"""Tests for the resilient HTTP client (retries + circuit breaker)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from {{ cookiecutter.package_name }}.core.http import (
    CircuitBreaker,
    CircuitOpenError,
    ResilientHttpClient,
)


async def test_retries_then_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 2:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    client = ResilientHttpClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    response = await client.get("http://svc/")
    assert response.status_code == 200
    assert calls == 2  # one retry
    await client.aclose()


async def test_4xx_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404)

    client = ResilientHttpClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    response = await client.get("http://svc/")
    assert response.status_code == 404
    assert calls == 1  # client errors are not retried
    await client.aclose()


async def test_circuit_breaker_opens_and_recovers() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=0.05)
    for _ in range(2):
        with pytest.raises(ValueError, match="boom"):
            async with breaker:
                raise ValueError("boom")

    with pytest.raises(CircuitOpenError):
        async with breaker:
            pass  # open -> fails fast

    await asyncio.sleep(0.06)  # past reset_timeout -> half-open allows a trial
    async with breaker:
        pass  # a success closes the breaker again
