"""Tests for request-id propagation, the access log and security headers."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from {{ cookiecutter.package_name }}.core import middleware as middleware_module
from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.main import create_app

API = settings.api_v1_prefix


class RecordingLogger:
    """Captures structlog-style log calls made by the middleware."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def info(self, event: str, **kwargs: Any) -> None:
        self.events.append((event, kwargs))


@pytest_asyncio.fixture
async def light_client() -> AsyncIterator[AsyncClient]:
    """App-only client: no lifespan, no database — /health touches neither."""
    app = create_app()
{%- if cookiecutter.use_rate_limiting == "yes" %}
    app.state.limiter.enabled = False
{%- endif %}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def test_request_id_is_echoed(light_client: AsyncClient) -> None:
    response = await light_client.get(f"{API}/health", headers={"X-Request-ID": "abc-123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "abc-123"


async def test_request_id_is_generated_when_absent(light_client: AsyncClient) -> None:
    response = await light_client.get(f"{API}/health")
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


async def test_oversized_request_id_is_replaced(light_client: AsyncClient) -> None:
    response = await light_client.get(
        f"{API}/health",
        headers={"X-Request-ID": "x" * 129},
    )
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


async def test_security_headers_present(light_client: AsyncClient) -> None:
    response = await light_client.get(f"{API}/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    csp = response.headers["Content-Security-Policy"]
    assert csp == "default-src 'none'; frame-ancestors 'none'"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    # HSTS is production-only; the test environment runs as `local`.
    assert "Strict-Transport-Security" not in response.headers


async def test_docs_pages_are_self_hosted(light_client: AsyncClient) -> None:
    for path in ("/docs", "/redoc"):
        response = await light_client.get(path)
        assert response.status_code == 200
        assert "cdn.jsdelivr.net" not in response.text
        assert "/static/" in response.text
        csp = response.headers["Content-Security-Policy"]
        assert "script-src 'self' 'unsafe-inline'" in csp


async def test_request_completed_event(
    light_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = RecordingLogger()
    monkeypatch.setattr(middleware_module, "logger", recorder)

    response = await light_client.get(f"{API}/health")

    events = [fields for event, fields in recorder.events if event == "request_completed"]
    assert len(events) == 1
    fields = events[0]
    assert fields["method"] == "GET"
    assert fields["path"] == f"{API}/health"
    assert fields["status_code"] == 200
    assert fields["duration_ms"] >= 0
    assert fields["request_id"] == response.headers["X-Request-ID"]
