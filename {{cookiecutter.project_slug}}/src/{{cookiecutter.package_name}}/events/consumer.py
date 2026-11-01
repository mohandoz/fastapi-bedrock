"""Consume the events stream with a consumer group (at-least-once)."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any, cast

import redis.asyncio as redis
import structlog
from redis.exceptions import ResponseError

from {{ cookiecutter.package_name }}.core.config import settings

logger = structlog.get_logger(__name__)

_BACKOFF_INITIAL_S = 1.0
_BACKOFF_MAX_S = 30.0


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
    # Event values often contain customer data or credentials. Keep the useful
    # routing metadata without copying arbitrary payloads into shared logs.
    logger.info(
        "event.handle",
        event_type=event_type,
        event_id=event_id,
        payload_fields=sorted(payload),
    )


async def _dispatch(client: redis.Redis, message_id: str, fields: dict[str, str]) -> bool:
    try:
        await handle_event(fields["type"], json.loads(fields["data"]), event_id=fields["id"])
    except Exception:
        logger.exception("event.handle_failed", message_id=message_id)
        return False  # leave it pending in the PEL for XAUTOCLAIM to retry
    await client.xack(settings.redis_stream, settings.redis_consumer_group, message_id)
    return True


async def _dead_letter_if_exhausted(
    client: redis.Redis,
    message_id: str,
    fields: dict[str, str],
) -> None:
    pending = cast(
        "Any",
        await client.xpending_range(
            settings.redis_stream,
            settings.redis_consumer_group,
            min=message_id,
            max=message_id,
            count=1,
        ),
    )
    if not pending or pending[0]["times_delivered"] < settings.redis_max_delivery_attempts:
        return
    # One Redis transaction owns both state changes. A crash or connection loss
    # can therefore never publish a DLQ copy while leaving the source pending
    # (which would publish another copy on the next reclaim).
    async with client.pipeline(transaction=True) as pipe:
        pipe.xadd(
            settings.redis_dead_letter_stream,
            cast("Any", {**fields, "original_message_id": message_id}),
            maxlen=settings.redis_stream_maxlen,
            approximate=True,
        )
        pipe.xack(settings.redis_stream, settings.redis_consumer_group, message_id)
        await pipe.execute()
    logger.error(
        "event.dead_lettered",
        message_id=message_id,
        deliveries=pending[0]["times_delivered"],
    )


async def reclaim_stale(
    client: redis.Redis, consumer_name: str, *, min_idle_ms: int = 60_000
) -> None:
    """Reclaim entries stuck in any consumer's PEL for ``min_idle_ms``, then process them.

    Covers both entries orphaned by crashed replicas and this consumer's own
    failed messages (left unacked by ``_dispatch``).
    """
    cursor = "0-0"
    while True:
        # Redis 6.2 replies (cursor, messages); 7.0+ appends a deleted-ids list.
        cursor, claimed, *_ = await client.xautoclaim(
            name=settings.redis_stream,
            groupname=settings.redis_consumer_group,
            consumername=consumer_name,
            min_idle_time=min_idle_ms,
            start_id=cursor,
        )
        for message_id, fields in claimed:
            if not await _dispatch(client, message_id, fields):
                await _dead_letter_if_exhausted(client, message_id, fields)
        if cursor == "0-0":
            break


async def trim_processed(client: redis.Redis) -> None:
    """``XTRIM MINID`` entries the consumer group has fully processed.

    Never trims past the oldest still-pending entry (or the group's
    last-delivered-id), so unprocessed backlog is preserved; the
    ``redis_stream_maxlen`` cap on XADD remains the hard memory bound.
    Assumes this service's group is the stream's only consumer group —
    take the minimum across groups if you add more.
    """
    groups = cast("Any", await client.xinfo_groups(settings.redis_stream))
    group = next((g for g in groups if g["name"] == settings.redis_consumer_group), None)
    if group is None:
        return
    minid = group["last-delivered-id"]
    summary = cast(
        "Any", await client.xpending(settings.redis_stream, settings.redis_consumer_group)
    )
    if summary["pending"]:
        minid = summary["min"]
    await client.xtrim(settings.redis_stream, minid=minid, approximate=True)


async def consume(
    client: redis.Redis,
    consumer_name: str,
    *,
    stop: asyncio.Event,
    block_ms: int = 5000,
    count: int = 10,
    housekeeping_every_s: float = 60.0,
) -> None:
    """Long-running loop: read never-delivered entries, process, XACK each.

    Every ``housekeeping_every_s`` the loop also reclaims stale PEL entries
    (so failed messages are retried while the worker is alive, not only at
    boot) and trims fully processed entries from the stream. Transient errors
    are logged and retried with exponential backoff instead of killing the
    worker.
    """
    logger.info("event.consumer.start", group=settings.redis_consumer_group, consumer=consumer_name)
    delay = _BACKOFF_INITIAL_S
    next_housekeeping = 0.0  # 0.0 -> first iteration recovers orphaned backlog on boot
    while not stop.is_set():
        try:
            now = asyncio.get_running_loop().time()
            if now >= next_housekeeping:
                await ensure_group(client)
                await reclaim_stale(client, consumer_name)
                await trim_processed(client)
                next_housekeeping = now + housekeeping_every_s
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
            for _stream, entries in response or []:
                for message_id, fields in entries:
                    if not await _dispatch(client, message_id, fields):
                        # Check the first delivery too: a configured maximum of
                        # one attempt must not invoke the handler a second time.
                        await _dead_letter_if_exhausted(client, message_id, fields)
        except Exception:
            logger.exception("event.consumer.error", retry_in_s=delay)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)
            delay = min(delay * 2, _BACKOFF_MAX_S)
        else:
            delay = _BACKOFF_INITIAL_S
