"""Application factory and ASGI entrypoint."""

from __future__ import annotations

{% if cookiecutter.use_temporal == "yes" -%}
import asyncio
{% endif -%}
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
{%- if cookiecutter.use_redis == "yes" and cookiecutter.use_observability == "yes" %}
from opentelemetry.instrumentation.redis import RedisInstrumentor
{%- endif %}
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from {{ cookiecutter.package_name }}.api.router import api_router
from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import dispose_db, init_db
from {{ cookiecutter.package_name }}.core.exceptions import add_exception_handlers
{%- if cookiecutter.use_http_client == "yes" %}
from {{ cookiecutter.package_name }}.core.http import create_http_client
{%- endif %}
from {{ cookiecutter.package_name }}.core.logging import configure_logging
from {{ cookiecutter.package_name }}.core.middleware import (
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
{%- if cookiecutter.use_observability == "yes" %}
from {{ cookiecutter.package_name }}.core.observability import (
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
{%- if cookiecutter.use_observability == "yes" %}
    # Attach OTLP exporters AFTER configure_logging() (it reassigns root.handlers).
    configure_observability(app)
{%- endif %}
{%- if cookiecutter.use_sentry == "yes" %}
    init_sentry()
{%- endif %}
{%- if cookiecutter.use_temporal == "yes" %}
    # The Temporal client connects lazily on first use (see temporal/client.py).
    app.state.temporal_client = None
    app.state.temporal_lock = asyncio.Lock()
{%- endif %}
{%- if cookiecutter.use_redis == "yes" %}
    # Built once here; redis-py opens no socket until the first command.
    app.state.redis = create_redis_client()
{%- if cookiecutter.use_observability == "yes" %}
    RedisInstrumentor().instrument()
{%- endif %}
{%- endif %}
{%- if cookiecutter.use_http_client == "yes" %}
    app.state.http_client = create_http_client()
{%- endif %}
    # Auto-create tables only for local development; staging/production use Alembic.
    if settings.is_local:
        await init_db()
    yield
{%- if cookiecutter.use_redis == "yes" %}
    await app.state.redis.aclose()
{%- endif %}
{%- if cookiecutter.use_http_client == "yes" %}
    await app.state.http_client.aclose()
{%- endif %}
    await dispose_db()
{%- if cookiecutter.use_observability == "yes" %}
    shutdown_observability(app)  # flush batch exporters before exit
{%- endif %}


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=settings.project_name,
        version=settings.version,
        description=settings.description,
        contact={"name": settings.contact_name, "email": settings.contact_email},
        license_info={"name": "MIT", "identifier": "MIT"},
        debug=settings.debug,
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json" if settings.docs_enabled else None,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
    )

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

    add_exception_handlers(app)
{%- if cookiecutter.use_rate_limiting == "yes" %}
    add_rate_limiting(app)
{%- endif %}
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
