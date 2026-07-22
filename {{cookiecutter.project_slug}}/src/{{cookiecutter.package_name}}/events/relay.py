"""Outbox relay: forward committed outbox rows to the Redis Stream."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import redis.asyncio as redis
import structlog
from sqlmodel import col, select

from {{ cookiecutter.package_name }}.core.database import async_session_factory
from {{ cookiecutter.package_name }}.events.models import OutboxEvent
from {{ cookiecutter.package_name }}.events.publisher import publish_event

logger = structlog.get_logger(__name__)


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
    re-delivery idempotent for consumers.
    """
    logger.info("outbox.relay.start")
    while not stop.is_set():
        async with async_session_factory() as session:
            result = await session.exec(
                select(OutboxEvent)
                .where(col(OutboxEvent.published_at).is_(None))
                .order_by(col(OutboxEvent.created_at))
                .limit(batch)
            )
            rows = result.all()
            for row in rows:
                await publish_event(client, row.event_type, row.payload, event_id=str(row.id))
                row.published_at = datetime.now(UTC)
                session.add(row)
            await session.commit()
        if not rows:
            await asyncio.sleep(poll_interval)
    logger.info("outbox.relay.stop")
