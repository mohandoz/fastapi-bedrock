"""Redis events worker: runs the outbox relay AND the Streams consumer.

Run as its own deployment:

    python -m {{ cookiecutter.package_name }}.events.worker
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import socket

import structlog

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.logging import configure_logging
from {{ cookiecutter.package_name }}.core.redis import create_redis_client
from {{ cookiecutter.package_name }}.events.consumer import consume
from {{ cookiecutter.package_name }}.events.relay import relay_outbox

logger = structlog.get_logger(__name__)


async def main() -> None:
    configure_logging()
    client = create_redis_client()
    consumer_name = socket.gethostname()  # unique per replica -> its own PEL slot

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    logger.info("event.worker.start", stream=settings.redis_stream)
    try:
        # TaskGroup cancels the sibling if one task fails and waits for both to
        # finish, so the shared client is only closed once no task is using it.
        async with asyncio.TaskGroup() as tg:
            tg.create_task(relay_outbox(client, stop=stop))
            tg.create_task(consume(client, consumer_name, stop=stop))
    finally:
        await client.aclose()
        logger.info("event.worker.stop")


if __name__ == "__main__":
    asyncio.run(main())
