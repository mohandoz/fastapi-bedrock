"""Tests for Redis: cache, distributed lock, and the Streams events pipeline.

The ``redis_client`` and ``session_factory`` fixtures live in conftest.py.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from {{ cookiecutter.package_name }}.core.cache import Cache
from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.lock import distributed_lock
from {{ cookiecutter.package_name }}.events import consumer as consumer_module
from {{ cookiecutter.package_name }}.events import relay as relay_module
from {{ cookiecutter.package_name }}.events.consumer import consume, ensure_group, reclaim_stale
from {{ cookiecutter.package_name }}.events.models import OutboxEvent
from {{ cookiecutter.package_name }}.events.publisher import enqueue_event, publish_event
from {{ cookiecutter.package_name }}.events.relay import relay_outbox


# --- Cache -----------------------------------------------------------------
async def test_cache_set_get(redis_client: redis.Redis) -> None:
    cache = Cache(redis_client)
    await cache.set("k", {"a": 1}, ttl=60)
    assert await cache.get("k") == {"a": 1}
    assert await cache.get("missing") is None


async def test_cache_get_or_set(redis_client: redis.Redis) -> None:
    cache = Cache(redis_client)
    calls = 0

    async def factory() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"v": 42}

    assert await cache.get_or_set("k2", factory) == {"v": 42}
    assert await cache.get_or_set("k2", factory) == {"v": 42}  # served from cache
    assert calls == 1


async def test_cache_delete(redis_client: redis.Redis) -> None:
    cache = Cache(redis_client)
    await cache.set("k3", "v")
    assert await cache.delete("k3") == 1
    assert await cache.get("k3") is None


# --- Distributed lock ------------------------------------------------------
async def test_distributed_lock(redis_client: redis.Redis) -> None:
    async with distributed_lock(redis_client, "job", blocking=False) as acquired:
        assert acquired is True
        async with distributed_lock(redis_client, "job", blocking=False) as second:
            assert second is False  # already held
    async with distributed_lock(redis_client, "job", blocking=False) as again:
        assert again is True  # released -> re-acquirable


# --- Streams (CloudEvents) -------------------------------------------------
async def test_publish_and_read_event(redis_client: redis.Redis) -> None:
    await ensure_group(redis_client)
    message_id = await publish_event(redis_client, "item.created", {"id": "abc"})
    assert message_id
    response = cast(
        "Any",
        await redis_client.xreadgroup(
            groupname=settings.redis_consumer_group,
            consumername="test",
            streams={settings.redis_stream: ">"},
            count=1,
        ),
    )
    _stream, entries = response[0]
    _mid, fields = entries[0]
    assert fields["type"] == "item.created"
    assert fields["specversion"] == "1.0"  # CloudEvents envelope


async def test_consume_processes_and_acks(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, dict[str, object]]] = []
    stop = asyncio.Event()

    async def fake_handle(event_type: str, payload: dict[str, object], *, event_id: str) -> None:
        seen.append((event_type, payload))
        stop.set()

    monkeypatch.setattr(consumer_module, "handle_event", fake_handle)
    await publish_event(redis_client, "item.created", {"id": "1"})
    await asyncio.wait_for(consume(redis_client, "consumer-1", stop=stop, block_ms=500), timeout=15)
    assert seen == [("item.created", {"id": "1"})]
    pending = cast(
        "Any",
        await redis_client.xpending(settings.redis_stream, settings.redis_consumer_group),
    )
    assert pending["pending"] == 0  # the processed message was XACKed out of the PEL


async def test_consume_failure_leaves_pending_until_reclaimed(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A raising handler must NOT ack; ``reclaim_stale`` re-delivers, then acks."""
    delivered: list[str] = []
    stop = asyncio.Event()

    async def failing_handle(event_type: str, payload: dict[str, object], *, event_id: str) -> None:
        delivered.append(event_id)
        stop.set()
        raise RuntimeError("handler exploded")

    monkeypatch.setattr(consumer_module, "handle_event", failing_handle)
    await publish_event(redis_client, "item.created", {"id": "1"})
    await asyncio.wait_for(consume(redis_client, "consumer-1", stop=stop, block_ms=500), timeout=15)
    pending = cast(
        "Any",
        await redis_client.xpending(settings.redis_stream, settings.redis_consumer_group),
    )
    assert pending["pending"] == 1  # failed message stays un-acked in the PEL

    async def ok_handle(event_type: str, payload: dict[str, object], *, event_id: str) -> None:
        delivered.append(event_id)

    monkeypatch.setattr(consumer_module, "handle_event", ok_handle)
    await reclaim_stale(redis_client, "consumer-2", min_idle_ms=0)

    pending = cast(
        "Any",
        await redis_client.xpending(settings.redis_stream, settings.redis_consumer_group),
    )
    assert pending["pending"] == 0  # reclaimed, re-dispatched, and acked
    assert len(delivered) == 2
    assert delivered[0] == delivered[1]  # same CloudEvents id across redeliveries


# --- Transactional outbox --------------------------------------------------
async def test_enqueue_event_persists(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        event = await enqueue_event(session, "item.created", {"id": "1"})
        await session.commit()
        event_id = event.id

    async with session_factory() as session:
        row = await session.get(OutboxEvent, event_id)
    assert row is not None
    assert row.published_at is None
    assert row.event_type == "item.created"


async def test_outbox_relay_publishes(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis.Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(relay_module, "async_session_factory", session_factory)
    async with session_factory() as session:
        await enqueue_event(session, "item.created", {"id": "42"})
        await session.commit()

    stop = asyncio.Event()

    async def stopper() -> None:
        await asyncio.sleep(0.5)
        stop.set()

    await asyncio.gather(relay_outbox(redis_client, stop=stop, poll_interval=0.05), stopper())

    assert await redis_client.xlen(settings.redis_stream) == 1
    async with session_factory() as session:
        rows = (await session.exec(select(OutboxEvent))).all()
    assert rows[0].published_at is not None
