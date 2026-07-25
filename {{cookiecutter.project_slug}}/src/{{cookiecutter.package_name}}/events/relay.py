"""Outbox relay: forward committed outbox rows to the Redis Stream.

``FOR UPDATE SKIP LOCKED`` on the outbox select lets concurrent relay
replicas partition the unpublished batch safely — each row is published by
exactly one replica per poll. Run a single relay replica (or add leader
election) if global event ordering matters.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

import redis.asyncio as redis
import structlog
from sqlmodel import col, select

from {{ cookiecutter.package_name }}.core.database import async_session_factory
from {{ cookiecutter.package_name }}.events.models import OutboxEvent
from {{ cookiecutter.package_name }}.events.publisher import publish_event

logger = structlog.get_logger(__name__)

_BACKOFF_INITIAL_S = 1.0
_BACKOFF_MAX_S = 30.0


async def relay_outbox(
    client: redis.Redis,
    *,
    stop: asyncio.Event,
    poll_interval: float = 1.0,
    batch: int = 100,
) -> None:
    """Poll unpublished outbox rows and forward them to the stream (at-least-once).

    If the process dies after publishing but before the commit, the row stays
    unpublished and is re-sent on restart; the CloudEvents id keeps that
    re-delivery idempotent for consumers. Transient DB/Redis errors are logged
    and retried with exponential backoff instead of killing the worker.
    """
    logger.info("outbox.relay.start")
    delay = _BACKOFF_INITIAL_S
    while not stop.is_set():
        try:
            async with async_session_factory() as session:
                result = await session.exec(
                    select(OutboxEvent)
                    .where(col(OutboxEvent.published_at).is_(None))
                    .order_by(col(OutboxEvent.created_at))
                    .limit(batch)
                    # Rows locked by another relay replica are skipped, not re-published.
                    .with_for_update(skip_locked=True)
                )
                rows = result.all()
                for row in rows:
                    await publish_event(client, row.event_type, row.payload, event_id=str(row.id))
                    row.published_at = datetime.now(UTC)
                    session.add(row)
                await session.commit()
        except Exception:
            logger.exception("outbox.relay.error", retry_in_s=delay)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)
            delay = min(delay * 2, _BACKOFF_MAX_S)
            continue
        delay = _BACKOFF_INITIAL_S
        if not rows:
            await asyncio.sleep(poll_interval)
    logger.info("outbox.relay.stop")
