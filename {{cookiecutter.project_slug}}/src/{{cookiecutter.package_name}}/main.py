"""Application factory and ASGI entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from {{ cookiecutter.package_name }}.api.router import api_router
from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import dispose_db, init_db
from {{ cookiecutter.package_name }}.core.exceptions import add_exception_handlers
from {{ cookiecutter.package_name }}.core.logging import configure_logging
from {{ cookiecutter.package_name }}.core.middleware import RequestIDMiddleware
{%- if cookiecutter.use_rate_limiting == "yes" %}
from {{ cookiecutter.package_name }}.core.rate_limit import add_rate_limiting
{%- endif %}
{%- if cookiecutter.use_sentry == "yes" %}
from {{ cookiecutter.package_name }}.core.sentry import init_sentry
{%- endif %}


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
{%- if cookiecutter.use_sentry == "yes" %}
    init_sentry()
{%- endif %}
    # Auto-create tables outside production; production relies on Alembic.
    if not settings.is_production:
        await init_db()
    yield
    await dispose_db()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=settings.project_name,
        version=settings.version,
        debug=settings.debug,
        lifespan=lifespan,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(RequestIDMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    add_exception_handlers(app)
{%- if cookiecutter.use_rate_limiting == "yes" %}
    add_rate_limiting(app)
{%- endif %}
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
