"""Publish domain events: transactional outbox (reliable) + direct Redis Stream.

Stream messages use the CloudEvents 1.0 envelope, so the CloudEvents ``id``
doubles as a stable idempotency key across at-least-once redeliveries.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import redis.asyncio as redis
import structlog
from sqlmodel.ext.asyncio.session import AsyncSession

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.events.models import OutboxEvent

logger = structlog.get_logger(__name__)

EVENT_SOURCE = "{{ cookiecutter.package_name }}"


def build_cloudevent(event_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, str]:
    """Flatten a CloudEvents 1.0 event to string stream fields."""
    return {
        "id": event_id,
        "source": EVENT_SOURCE,
        "type": event_type,
        "specversion": "1.0",
        "time": datetime.now(UTC).isoformat(),
        "datacontenttype": "application/json",
        "data": json.dumps(payload, default=str),
    }


async def publish_event(
    client: redis.Redis,
    event_type: str,
    payload: dict[str, Any],
    *,
    event_id: str | None = None,
) -> str:
    """Publish a CloudEvent directly to the stream (used by the outbox relay and
    for fire-and-forget events). Returns the stream entry id.

    Retention: the consumer trims processed entries (``XTRIM MINID``), so
    ``settings.redis_stream_maxlen`` acts only as an approximate hard cap on
    unprocessed backlog — events are lost if consumers lag by more than that
    many entries. Monitor ``XLEN`` / ``XPENDING`` and alert well below the cap.
    """
    fields = build_cloudevent(event_id or uuid.uuid4().hex, event_type, payload)
    message_id = cast(
        "str",
        # redis-py types the field mapping invariantly; our str->str dict is fine.
        await client.xadd(
            settings.redis_stream,
            cast("Any", fields),
            maxlen=settings.redis_stream_maxlen,
            approximate=True,
        ),
    )
    logger.info(
        "event.published", event_type=event_type, event_id=fields["id"], message_id=message_id
    )
    return message_id


async def enqueue_event(
    session: AsyncSession, event_type: str, payload: dict[str, Any]
) -> OutboxEvent:
    """Persist an event to the outbox IN THE CALLER'S TRANSACTION.

    It commits atomically with the caller's domain changes; the relay (the events
    worker) forwards it to the stream afterwards. This is the transactional
    outbox pattern.
    """
    event = OutboxEvent(event_type=event_type, payload=payload)
    session.add(event)
    await session.flush()
    logger.debug("event.enqueued", event_type=event_type, event_id=str(event.id))
    return event
