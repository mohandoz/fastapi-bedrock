"""Tests for RFC 9457 ``application/problem+json`` error responses."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from {{ cookiecutter.package_name }}.core import middleware as middleware_module
from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.exceptions import NotFoundError, UnauthorizedError
from {{ cookiecutter.package_name }}.main import create_app

API = settings.api_v1_prefix


class RecordingLogger:
    """Captures structlog-style log calls made by the middleware."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def info(self, event: str, **kwargs: Any) -> None:
        self.events.append((event, kwargs))


def _build_app() -> FastAPI:
    """The real app plus routes exercising each error path."""
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("kaboom")

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError("Widget 42 not found")

    @app.get("/locked")
    async def locked() -> None:
        raise UnauthorizedError()

    @app.get("/validated")
    async def validated(count: int) -> dict[str, int]:
        return {"count": count}

    return app


@pytest_asyncio.fixture
async def error_client() -> AsyncIterator[AsyncClient]:
    app = _build_app()
{%- if cookiecutter.use_rate_limiting == "yes" %}
    app.state.limiter.enabled = False
{%- endif %}
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def test_app_error_renders_problem(error_client: AsyncClient) -> None:
    response = await error_client.get("/missing")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "urn:problem-type:not-found",
        "title": "Not Found",
        "status": 404,
        "detail": "Widget 42 not found",
        "instance": "/missing",
    }


async def test_unauthorized_problem_sets_www_authenticate(error_client: AsyncClient) -> None:
    response = await error_client.get("/locked")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    body = response.json()
    assert body["type"] == "urn:problem-type:unauthorized"
    assert body["status"] == 401


async def test_http_exception_renders_problem(error_client: AsyncClient) -> None:
    response = await error_client.get("/no-such-route")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Not Found"
    assert body["status"] == 404


async def test_validation_error_renders_problem(error_client: AsyncClient) -> None:
    response = await error_client.get("/validated", params={"count": "not-a-number"})
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["type"] == "urn:problem-type:validation-error"
    assert body["title"] == "Validation Error"
    assert body["status"] == 422
    assert body["errors"], "validation problems must carry the failing fields"
    assert body["errors"][0]["loc"] == ["query", "count"]


async def test_unhandled_error_renders_sanitized_problem(
    error_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = RecordingLogger()
    monkeypatch.setattr(middleware_module, "logger", recorder)
    monkeypatch.setattr(settings, "cors_origins", ["https://app.example"])

    response = await error_client.get(
        "/boom",
        headers={"X-Request-ID": "err-42", "Origin": "https://app.example"},
    )

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "urn:problem-type:internal-error",
        "title": "Internal Server Error",
        "status": 500,
        "detail": "Internal server error",
        "instance": "/boom",
    }
    assert "kaboom" not in response.text
    # Rendered by the outermost error handler, the 500 bypasses both middleware
    # yet must still carry the request id and security headers.
    assert response.headers["X-Request-ID"] == "err-42"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Access-Control-Allow-Origin"] == "https://app.example"
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    # ...and the access log still records the failed request.
    completed = [fields for event, fields in recorder.events if event == "request_completed"]
    assert completed and completed[0]["status_code"] == 500


async def test_openapi_documents_problem_responses(error_client: AsyncClient) -> None:
    response = await error_client.get(f"{API}/openapi.json")
    assert response.status_code == 200
    responses = response.json()["paths"][f"{API}/health"]["get"]["responses"]
    assert "application/problem+json" in responses["422"]["content"]
    assert "application/problem+json" in responses["500"]["content"]
