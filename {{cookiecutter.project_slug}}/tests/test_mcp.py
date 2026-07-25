{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
"""Tests for the MCP server: curated tools via the in-memory FastMCP client.

The in-memory transport drives the real MCP protocol but bypasses the HTTP
layer{% if cookiecutter.use_auth == "yes" %}, so bearer-token enforcement is covered separately against the
verifier itself{% endif %}.
"""

from __future__ import annotations

{% if cookiecutter.use_auth == "yes" -%}
import uuid

{% endif -%}
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from {{ cookiecutter.package_name }}.mcp import server as mcp_server

UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def mcp_db(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Point the MCP tools' session factory at the testcontainers database."""
    monkeypatch.setattr(mcp_server, "async_session_factory", session_factory)


async def test_create_and_get_roundtrip(mcp_db: None) -> None:
    async with Client(mcp_server.mcp) as client:
        created = await client.call_tool(
            "create_{{ cookiecutter.first_entity }}", {"name": "agent-made", "description": "via MCP"}
        )
        body = created.structured_content
        assert body is not None
        assert body["name"] == "agent-made"
        assert body["id"]

        fetched = await client.call_tool("get_{{ cookiecutter.first_entity }}", {"{{ cookiecutter.first_entity }}_id": body["id"]})
        fetched_body = fetched.structured_content
        assert fetched_body is not None
        assert fetched_body["id"] == body["id"]


async def test_list_paginates_and_reports_total(mcp_db: None) -> None:
    async with Client(mcp_server.mcp) as client:
        for name in ("first", "second"):
            await client.call_tool("create_{{ cookiecutter.first_entity }}", {"name": name})
        result = await client.call_tool("list_{{ cookiecutter.first_entity }}s", {"limit": 1})
        body = result.structured_content
        assert body is not None
        assert body["total"] >= 2
        assert len(body["items"]) == 1


async def test_get_unknown_raises_tool_error(mcp_db: None) -> None:
    async with Client(mcp_server.mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("get_{{ cookiecutter.first_entity }}", {"{{ cookiecutter.first_entity }}_id": UNKNOWN_ID})


async def test_expected_tools_are_registered() -> None:
    async with Client(mcp_server.mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    expected = {
        "list_{{ cookiecutter.first_entity }}s",
        "get_{{ cookiecutter.first_entity }}",
        "create_{{ cookiecutter.first_entity }}",
    }
    assert expected <= set(tools)
    # Descriptions feed LLM tool selection — never ship blank ones.
    assert all(tools[name].description for name in expected)
{%- if cookiecutter.use_auth == "yes" %}


async def test_verifier_accepts_access_tokens() -> None:
    from {{ cookiecutter.package_name }}.core.security import create_access_token
    from {{ cookiecutter.package_name }}.mcp.auth import build_token_verifier

    verifier = build_token_verifier()
    access = await verifier.verify_token(create_access_token(uuid.uuid4()))
    assert access is not None
    assert access.claims["type"] == "access"


async def test_verifier_rejects_refresh_and_garbage_tokens() -> None:
    from {{ cookiecutter.package_name }}.core.security import create_refresh_token
    from {{ cookiecutter.package_name }}.mcp.auth import build_token_verifier

    verifier = build_token_verifier()
    refresh = create_refresh_token(uuid.uuid4(), jti=uuid.uuid4().hex, family=uuid.uuid4().hex)
    assert await verifier.verify_token(refresh) is None
    assert await verifier.verify_token("not-a-jwt") is None
{%- endif %}
