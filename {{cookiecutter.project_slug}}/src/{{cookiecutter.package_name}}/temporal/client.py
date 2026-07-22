"""Temporal client lifecycle and the FastAPI dependency that hands it out."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, Request
from temporalio.client import Client

from {{ cookiecutter.package_name }}.core.config import settings

logger = structlog.get_logger(__name__)


async def connect_temporal() -> Client:
    """Open a single shared Temporal client (used by the API and the worker)."""
    logger.info(
        "temporal.connect",
        host=settings.temporal_host,
        namespace=settings.temporal_namespace,
    )
    return await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
        # For Temporal Cloud, also pass: api_key=..., tls=True
    )


async def get_temporal_client(request: Request) -> Client:
    """Return the process-wide client, connecting once on first use.

    The client is cached on ``app.state`` (initialised in the lifespan) so every
    request reuses the same connection-pooled object; the lock makes the first
    concurrent requests connect exactly once.
    """
    state = request.app.state
    client: Client | None = getattr(state, "temporal_client", None)
    if client is not None:
        return client
    async with state.temporal_lock:
        client = getattr(state, "temporal_client", None)  # double-checked
        if client is None:
            client = await connect_temporal()
            state.temporal_client = client
    return client


TemporalClient = Annotated[Client, Depends(get_temporal_client)]
