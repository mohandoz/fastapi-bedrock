"""Application factory and ASGI entrypoint."""

from __future__ import annotations

{% if cookiecutter.use_temporal == "yes" -%}
import asyncio
{% endif -%}
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from {{ cookiecutter.package_name }}.api.router import api_router
from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import dispose_db, init_db
from {{ cookiecutter.package_name }}.core.exceptions import PROBLEM_RESPONSES, add_exception_handlers
{%- if cookiecutter.use_http_client == "yes" %}
from {{ cookiecutter.package_name }}.core.http import create_http_client
{%- endif %}
from {{ cookiecutter.package_name }}.core.limits import (
    BodySizeLimitMiddleware,
    RequestTimeoutMiddleware,
    install_shutdown_drain,
)
from {{ cookiecutter.package_name }}.core.logging import configure_logging
from {{ cookiecutter.package_name }}.core.middleware import (
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
{%- if cookiecutter.use_observability == "yes" %}
from {{ cookiecutter.package_name }}.core.observability import (
    attach_otel_log_handler,
    configure_observability,
    shutdown_observability,
)
{%- endif %}
{%- if cookiecutter.use_rate_limiting == "yes" %}
from {{ cookiecutter.package_name }}.core.rate_limit import add_rate_limiting
{%- endif %}
{%- if cookiecutter.use_redis == "yes" %}
from {{ cookiecutter.package_name }}.core.redis import create_redis_client
{%- endif %}
{%- if cookiecutter.use_sentry == "yes" %}
from {{ cookiecutter.package_name }}.core.sentry import init_sentry
{%- endif %}
{%- if cookiecutter.use_auth == "yes" %}
from {{ cookiecutter.package_name }}.domains.auth.bootstrap import ensure_first_superuser
{%- endif %}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    # SIGTERM flips app.state.shutting_down so /ready 503s and load balancers
    # drain us; must run here (not create_app) so uvicorn's own signal handler
    # is already installed and gets chained.
    install_shutdown_drain(app)
{%- if cookiecutter.use_observability == "yes" %}
    # Attach the OTLP log handler AFTER configure_logging() (it reassigns root.handlers).
    attach_otel_log_handler(app)
{%- endif %}
{%- if cookiecutter.use_sentry == "yes" %}
    init_sentry()
{%- endif %}
{%- if cookiecutter.use_temporal == "yes" %}
    # The Temporal client connects lazily on first use (see temporal/client.py).
    app.state.temporal_client = None
    app.state.temporal_lock = asyncio.Lock()
{%- endif %}
    # LIFO teardown: every step runs even if another raises, and a startup
    # failure below unwinds whatever was already created.
    async with AsyncExitStack() as stack:
{%- if cookiecutter.use_observability == "yes" %}
        stack.callback(shutdown_observability, app)  # flush batch exporters last
{%- endif %}
        stack.push_async_callback(dispose_db)
{%- if cookiecutter.use_redis == "yes" %}
        # Built once here; redis-py opens no socket until the first command.
        app.state.redis = create_redis_client()
        stack.push_async_callback(app.state.redis.aclose)
{%- endif %}
{%- if cookiecutter.use_http_client == "yes" %}
        app.state.http_client = create_http_client()
        stack.push_async_callback(app.state.http_client.aclose)
{%- endif %}
        # No-op unless db_auto_create is enabled (local default); see migrations/README.
        await init_db()
{%- if cookiecutter.use_auth == "yes" %}
        # Create or promote the FIRST_SUPERUSER account (no-op unless configured).
        await ensure_first_superuser()
{%- endif %}
        yield


def generate_unique_route_id(route: APIRoute) -> str:
    """Tag-based operation IDs (e.g. ``items-list_items``) so generated clients get clean method names."""
    if route.tags:
        return f"{route.tags[0]}-{route.name}"
    return route.name


def _install_docs_routes(app: FastAPI) -> None:
    """Serve /docs and /redoc from the vendored assets in core/static.

    No CDN: the pages load only self-hosted JS/CSS, so they work air-gapped and
    run under the strict docs CSP set by SecurityHeadersMiddleware. Keep the
    paths in sync with ``_DOCS_PATHS`` in core/middleware.py.
    """
    static_dir = Path(__file__).parent / "core" / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    openapi_url = app.openapi_url or f"{settings.api_v1_prefix}/openapi.json"

    @app.get("/docs", include_in_schema=False)
    async def swagger_ui_html() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url=openapi_url,
            title=f"{settings.project_name} - Swagger UI",
            swagger_js_url="/static/swagger-ui-bundle.js",
            swagger_css_url="/static/swagger-ui.css",
            swagger_favicon_url="/static/favicon.png",
            # Bearer-token auth only; the OAuth2 redirect page is not needed.
            oauth2_redirect_url=None,
        )

    @app.get("/redoc", include_in_schema=False)
    async def redoc_html() -> HTMLResponse:
        return get_redoc_html(
            openapi_url=openapi_url,
            title=f"{settings.project_name} - ReDoc",
            redoc_js_url="/static/redoc.standalone.js",
            redoc_favicon_url="/static/favicon.png",
            with_google_fonts=False,  # required by the docs CSP (no external origins)
        )


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=settings.project_name,
        version=settings.version,
        description=settings.description,
        contact={"name": settings.contact_name, "email": settings.contact_email},
        license_info={"name": "MIT", "identifier": "MIT"},
        debug=settings.debug,
        generate_unique_id_function=generate_unique_route_id,
        lifespan=lifespan,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json" if settings.docs_enabled else None,
        # /docs and /redoc are served from vendored assets (core/static) by
        # _install_docs_routes below — no CDN JavaScript on token-handling pages.
        docs_url=None,
        redoc_url=None,
    )
    if settings.docs_enabled:
        _install_docs_routes(app)
{%- if cookiecutter.use_rate_limiting == "yes" %}

    # Registered FIRST so its middleware sits innermost: 429 responses still
    # pass through the CORS, request-ID and security-header middleware below.
    add_rate_limiting(app)
{%- endif %}

    # Innermost of the app-level middleware: 504s from the timeout still pass
    # through the security-header, CORS and request-id middleware below.
    app.add_middleware(RequestTimeoutMiddleware, timeout=settings.request_timeout)
    app.add_middleware(SecurityHeadersMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials="*" not in settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(RequestIDMiddleware)
    # Outermost: refuse oversized bodies before anything else buffers them.
    app.add_middleware(BodySizeLimitMiddleware, max_body_size=settings.max_body_size)

    add_exception_handlers(app)
{%- if cookiecutter.use_observability == "yes" %}
    # Must run before the app serves traffic; see configure_observability.
    configure_observability(app)
{%- endif %}
    # PROBLEM_RESPONSES documents 422/500 problem+json on every route and
    # replaces FastAPI's default HTTPValidationError 422 model.
    app.include_router(api_router, prefix=settings.api_v1_prefix, responses=PROBLEM_RESPONSES)
    return app


app = create_app()
