{% set entity_class = cookiecutter.first_entity | replace('_', ' ') | title | replace(' ', '') -%}
"""Temporal worker process: polls the task queue and runs workflows/activities.

Run as its own deployment (not inside the API process):

    python -m {{ cookiecutter.package_name }}.temporal.worker
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from datetime import timedelta

import structlog
from temporalio.worker import Worker

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.logging import configure_logging
from {{ cookiecutter.package_name }}.temporal.activities import process_{{ cookiecutter.first_entity }}_activity
from {{ cookiecutter.package_name }}.temporal.client import connect_temporal
from {{ cookiecutter.package_name }}.temporal.sandbox import sandbox_runner
from {{ cookiecutter.package_name }}.temporal.workflows import Process{{ entity_class }}Workflow

logger = structlog.get_logger(__name__)


async def main() -> None:
    configure_logging()
    client = await connect_temporal()
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[Process{{ entity_class }}Workflow],
        activities=[process_{{ cookiecutter.first_entity }}_activity],
        workflow_runner=sandbox_runner(),
        graceful_shutdown_timeout=timedelta(seconds=30),
        # Sync (`def`) activities would also need activity_executor=ThreadPoolExecutor(...).
    )

    # Drain in-flight activities on SIGTERM/SIGINT (e.g. `docker stop`).
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    logger.info("temporal.worker.start", task_queue=settings.temporal_task_queue)
    async with worker:
        await stop.wait()
    logger.info("temporal.worker.stop")


if __name__ == "__main__":
    asyncio.run(main())
