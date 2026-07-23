"""Liveness and readiness probes for orchestrators and load balancers."""

from __future__ import annotations

from fastapi import APIRouter
from sqlmodel import select

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
    session: SessionDep,
{%- if cookiecutter.use_redis == "yes" %}
    redis_client: RedisClient,
{%- endif %}
) -> dict[str, str]:
    await session.exec(select(1))
{%- if cookiecutter.use_redis == "yes" %}
    await redis_client.ping()
{%- endif %}
    return {"status": "ready"}
