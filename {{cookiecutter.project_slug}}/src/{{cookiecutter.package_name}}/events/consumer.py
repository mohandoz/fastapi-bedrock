"""Consume the events stream with a consumer group (at-least-once)."""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast

import redis.asyncio as redis
import structlog
from redis.exceptions import ResponseError

from {{ cookiecutter.package_name }}.core.config import settings

logger = structlog.get_logger(__name__)


async def ensure_group(client: redis.Redis) -> None:
    """Create the consumer group (idempotent); ``mkstream`` creates the stream."""
    try:
        await client.xgroup_create(
            name=settings.redis_stream,
            groupname=settings.redis_consumer_group,
            id="0",  # "0" replays backlog; "$" delivers only new messages
            mkstream=True,
        )
        logger.info("event.group.created", group=settings.redis_consumer_group)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):  # group already exists -> fine
            raise


async def handle_event(event_type: str, payload: dict[str, Any], *, event_id: str) -> None:
    """Domain handler. MUST be idempotent — the CloudEvents ``event_id`` is stable
    across at-least-once redeliveries, so use it to dedupe side effects.

    Dispatch to your domain services here, opening a DB session like a Temporal
    activity does.
    """
    logger.info("event.handle", event_type=event_type, event_id=event_id, payload=payload)


async def _dispatch(client: redis.Redis, message_id: str, fields: dict[str, str]) -> None:
    try:
        await handle_event(fields["type"], json.loads(fields["data"]), event_id=fields["id"])
    except Exception:
        logger.exception("event.handle_failed", message_id=message_id)
        return  # leave it pending in the PEL for XAUTOCLAIM to retry — do NOT ack
    await client.xack(settings.redis_stream, settings.redis_consumer_group, message_id)


async def reclaim_stale(client: redis.Redis, consumer_name: str, *, min_idle_ms: int = 60_000) -> None:
    """Reclaim entries stuck in a crashed consumer's PEL, then process them."""
    cursor = "0-0"
    while True:
        cursor, claimed, _deleted = await client.xautoclaim(
            name=settings.redis_stream,
            groupname=settings.redis_consumer_group,
            consumername=consumer_name,
            min_idle_time=min_idle_ms,
            start_id=cursor,
        )
        for message_id, fields in claimed:
            await _dispatch(client, message_id, fields)
        if cursor == "0-0":
            break


async def consume(
    client: redis.Redis,
    consumer_name: str,
    *,
    stop: asyncio.Event,
    block_ms: int = 5000,
    count: int = 10,
) -> None:
    """Long-running loop: read never-delivered entries, process, XACK each."""
    await ensure_group(client)
    await reclaim_stale(client, consumer_name)  # recover orphaned backlog on boot
    logger.info("event.consumer.start", group=settings.redis_consumer_group, consumer=consumer_name)
    while not stop.is_set():
        # redis-py's Streams return type is a broad bytes|str union; cast to the
        # concrete shape we get with decode_responses=True.
        response = cast(
            "Any",
            await client.xreadgroup(
                groupname=settings.redis_consumer_group,
                consumername=consumer_name,
                streams={settings.redis_stream: ">"},  # ">" = never-delivered entries
                count=count,
                block=block_ms,  # long-poll, then loop to re-check `stop`
            ),
        )
        if not response:
            continue
        for _stream, entries in response:
            for message_id, fields in entries:
                await _dispatch(client, message_id, fields)
