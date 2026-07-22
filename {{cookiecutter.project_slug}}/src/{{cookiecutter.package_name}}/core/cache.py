"""A small, explicit cache-aside helper over redis.asyncio (JSON values).

Use it from the service/domain layer, not as a decorator on path operations —
wrapping an endpoint hides its signature and breaks FastAPI's dependency
introspection.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, TypeVar, cast

import redis.asyncio as redis
import structlog
from fastapi import Depends

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.redis import RedisClient

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class Cache:
    """Thin cache-aside wrapper: JSON (de)serialisation + TTL, no magic."""

    def __init__(
        self,
        client: redis.Redis,
        *,
        prefix: str = "cache",
        default_ttl: int | None = None,
    ) -> None:
        self._redis = client
        self._prefix = prefix
        self._default_ttl = default_ttl if default_ttl is not None else settings.cache_default_ttl

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    async def get(self, key: str) -> Any | None:
        raw = await self._redis.get(self._key(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("cache.decode_error", key=key)
            return None

    async def set(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        await self._redis.set(
            self._key(key),
            json.dumps(value, default=str),
            ex=ttl if ttl is not None else self._default_ttl,
        )

    async def delete(self, *keys: str) -> int:
        if not keys:
            return 0
        return int(await self._redis.delete(*(self._key(k) for k in keys)))

    async def get_or_set(
        self, key: str, factory: Callable[[], Awaitable[T]], *, ttl: int | None = None
    ) -> T:
        """Return the cached value, or compute + store it on a miss."""
        cached = await self.get(key)
        if cached is not None:
            return cast("T", cached)
        value = await factory()
        await self.set(key, value, ttl=ttl)
        return value


def get_cache(client: RedisClient) -> Cache:
    return Cache(client)


CacheDep = Annotated[Cache, Depends(get_cache)]
