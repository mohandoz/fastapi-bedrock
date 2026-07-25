"""Serve ``/llms.txt`` — a machine-readable service index for coding agents.

IDE and coding agents (Claude Code, Cursor, Windsurf, Cline) fetch
``/llms.txt`` (https://llmstxt.org/) when pointed at a service. The document
is rendered from the OpenAPI schema, so route ``summary=`` metadata written
for humans doubles as the agent-facing index. Gated behind ``docs_enabled``:
it follows the same production-exposure policy as ``/docs``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.exceptions import NotFoundError

# Registered by main.create_app WITHOUT the API prefix: /llms.txt must live at
# the site root, and include_in_schema=False keeps it out of its own index.
router = APIRouter(include_in_schema=False)

_HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def render_llms_txt(schema: dict[str, Any]) -> str:
    """Render an llms.txt markdown document from an OpenAPI schema."""
    info = schema.get("info", {})
    lines: list[str] = [f"# {info.get('title', settings.project_name)}", ""]
    description = str(info.get("description") or "").strip()
    if description:
        lines += [f"> {description.splitlines()[0]}", ""]
    lines += [
        f"Version {info.get('version', settings.version)}. "
        f"JSON REST API under `{settings.api_v1_prefix}`; "
        "errors use RFC 9457 `application/problem+json`.",
{%- if cookiecutter.use_auth == "yes" %}
        "Authentication: OAuth2 bearer JWT — obtain a token via "
        f"`POST {settings.api_v1_prefix}/auth/login` "
        "(form fields `username`, `password`) and send it as "
        "`Authorization: Bearer <token>`.",
{%- else %}
        "Authentication: none (all routes are public).",
{%- endif %}
        "",
        "## Endpoints",
        "",
    ]
    for path, operations in schema.get("paths", {}).items():
        for method in _HTTP_METHODS:
            operation = operations.get(method)
            if operation is None:
                continue
            summary = operation.get("summary") or operation.get("operationId") or ""
            lines.append(f"- `{method.upper()} {path}`: {summary}")
    lines += [
        "",
        "## Machine-readable",
        "",
        f"- [OpenAPI 3.1 schema]({settings.api_v1_prefix}/openapi.json): "
        "full request/response contract",
        "- [Swagger UI](/docs) and [ReDoc](/redoc): interactive documentation",
{%- if cookiecutter.use_mcp == "yes" %}
        "- [MCP endpoint](/mcp): Model Context Protocol server "
        "(streamable HTTP) with curated tools",
{%- endif %}
    ]
    return "\n".join(lines) + "\n"


@router.get("/llms.txt")
async def llms_txt(request: Request) -> PlainTextResponse:
    """Serve the agent index, rendered once per process from the OpenAPI schema."""
    if not settings.docs_enabled:
        # Same policy as /docs: rendered as a problem+json 404 by the handlers.
        raise NotFoundError()
    rendered: str | None = getattr(request.app.state, "llms_txt", None)
    if rendered is None:
        rendered = render_llms_txt(request.app.openapi())
        request.app.state.llms_txt = rendered
    return PlainTextResponse(rendered, media_type="text/markdown")
