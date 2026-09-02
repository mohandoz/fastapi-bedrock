"""Redis client lifecycle and the FastAPI dependency that hands it out."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlsplit

import redis.asyncio as redis
import structlog
from fastapi import Depends, Request

from {{ cookiecutter.package_name }}.core.config import settings

logger = structlog.get_logger(__name__)


def create_redis_client() -> redis.Redis:
    """Build the process-wide async Redis client.

    Construction opens NO socket: redis-py connects lazily from its internal
    pool on the first command, so this is safe to call at startup. The client
    owns its pool (sized by ``max_connections``); close it once, on shutdown,
    with ``aclose()``. Reused by the API, the events worker and Temporal.
    """
    parsed = urlsplit(settings.redis_url)
    logger.info(
        "redis.client.create",
        host=parsed.hostname,
        port=parsed.port,
        database=parsed.path.lstrip("/") or "0",
        tls=parsed.scheme == "rediss",
    )
    return redis.from_url(
        settings.redis_url,
        max_connections=settings.redis_max_connections,
        decode_responses=True,  # str in/out (JSON cache + string stream fields)
        # redis-py 8 defaults: RESP3 on the wire, RESP2-compatible Python reply
        # shapes. Both are set explicitly so a future redis-py default flip
        # cannot silently change the reply shapes the events/ Streams consumer
        # (xreadgroup/xautoclaim) parses. Flipping legacy_responses to False is
        # a deliberate migration: re-run the testcontainers stream tests first.
        protocol=3,
        legacy_responses=True,
        health_check_interval=30,
        socket_keepalive=True,
        # Fail fast instead of wedging requests when Redis blackholes (redis-py
        # blocks forever by default); transient timeouts are retried by the
        # client's built-in Retry policy.
        socket_connect_timeout=5,
        socket_timeout=5,
    )


async def get_redis(request: Request) -> redis.Redis:
    """Return the shared client created in the lifespan (see main.py)."""
    client: redis.Redis = request.app.state.redis
    return client


RedisClient = Annotated[redis.Redis, Depends(get_redis)]
