"""Liveness and readiness probes for orchestrators and load balancers."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, status
from sqlmodel import select

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import SessionDep
{%- if cookiecutter.use_rate_limiting == "yes" %}
from {{ cookiecutter.package_name }}.core.rate_limit import limiter
{%- endif %}
{%- if cookiecutter.use_redis == "yes" %}
from {{ cookiecutter.package_name }}.core.redis import RedisClient
{%- endif %}

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
{%- if cookiecutter.use_rate_limiting == "yes" %}
@limiter.exempt
{%- endif %}
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe (verifies the database)")
{%- if cookiecutter.use_rate_limiting == "yes" %}
@limiter.exempt
{%- endif %}
async def ready(
    request: Request,
    session: SessionDep,
{%- if cookiecutter.use_redis == "yes" %}
    redis_client: RedisClient,
{%- endif %}
) -> dict[str, str]:
    if getattr(request.app.state, "shutting_down", False):
        # Draining after SIGTERM (see core.limits.install_shutdown_drain).
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Shutting down.",
        )
    try:
        # Bound every check so a wedged pool or dead dependency fails the
        # probe within its budget instead of hanging past it.
        await asyncio.wait_for(session.exec(select(1)), settings.readiness_check_timeout)
{%- if cookiecutter.use_redis == "yes" %}
        await asyncio.wait_for(redis_client.ping(), settings.readiness_check_timeout)
{%- endif %}
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dependency check timed out.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dependency check failed.",
        ) from exc
    return {"status": "ready"}
