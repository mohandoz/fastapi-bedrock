"""A lease-bounded Redis lock for leader election / cross-replica exclusion.

The lease can expire during a long event-loop stall or network partition, so
irreversible effects still need an idempotency key or fencing token.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

import redis.asyncio as redis
import structlog

logger = structlog.get_logger(__name__)


@contextlib.asynccontextmanager
async def distributed_lock(
    client: redis.Redis,
    name: str,
    *,
    ttl: float = 30.0,
    blocking: bool = True,
    blocking_timeout: float | None = 10.0,
) -> AsyncIterator[bool]:
    """Acquire a Redis lock (redis-py's Redlock-style ``Lock``).

    Yields ``True`` if the lock was acquired, ``False`` otherwise. The lock is
    released on exit and auto-expires after ``ttl`` seconds, so a crashed holder
    never deadlocks the others. Work must complete within ``ttl``::

        async with distributed_lock(redis, "nightly-report") as acquired:
            if acquired:
                await run_the_job()
    """
    lock = client.lock(name, timeout=ttl, blocking=blocking, blocking_timeout=blocking_timeout)
    acquired = await lock.acquire()
    try:
        if acquired:
            logger.debug("lock.acquired", name=name)
        yield acquired
    finally:
        if acquired:
            try:
                await lock.release()
                logger.debug("lock.released", name=name)
            except redis.RedisError:
                # Ownership loss and release-time outages are non-fatal: the
                # bounded lease expires on its own. Raising here would turn a
                # completed protected operation into a false failure/retry.
                logger.warning("lock.release_failed", name=name)
