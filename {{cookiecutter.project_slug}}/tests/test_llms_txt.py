"""Tests for the /llms.txt agent index (rendered from the OpenAPI schema)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from {{ cookiecutter.package_name }}.api.llms import router as llms_router
from {{ cookiecutter.package_name }}.api.router import api_router
from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.exceptions import add_exception_handlers

API = settings.api_v1_prefix


def build_app() -> FastAPI:
    """Minimal app mirroring how main.create_app registers the llms router."""
    app = FastAPI(
        title=settings.project_name,
        version=settings.version,
        description=settings.description,
    )
    add_exception_handlers(app)
    app.include_router(api_router, prefix=API)
    app.include_router(llms_router)
    return app


async def fetch_llms_txt(app: FastAPI) -> tuple[int, str, str]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/llms.txt")
    return response.status_code, response.headers.get("content-type", ""), response.text


async def test_llms_txt_indexes_the_service() -> None:
    status_code, content_type, body = await fetch_llms_txt(build_app())
    assert status_code == 200
    assert content_type.startswith("text/markdown")
    assert body.startswith(f"# {settings.project_name}")
    # Endpoint index carries the router summaries agents rely on.
    assert f"- `GET {API}/{{ cookiecutter.first_entity }}s`: " in body
    assert f"- `GET {API}/health`: " in body
    # Machine-readable links.
    assert f"{API}/openapi.json" in body
{%- if cookiecutter.use_auth == "yes" %}
    assert f"POST {API}/auth/login" in body
{%- else %}
    assert "Authentication: none" in body
{%- endif %}
{%- if cookiecutter.use_mcp == "yes" %}
    assert "(/mcp)" in body
{%- endif %}


async def test_llms_txt_follows_docs_enabled_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "docs_enabled", False)
    status_code, _, _ = await fetch_llms_txt(build_app())
    assert status_code == 404
