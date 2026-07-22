"""A resilient async HTTP client: timeouts + retries + a circuit breaker.

Hand-written and typed (no sidecar, no magic) — the outbound-call counterpart to
the retries Temporal gives inbound work. Injected via ``HttpClientDep``.
"""

from __future__ import annotations

import asyncio
import time
from types import TracebackType
from typing import Annotated, Any, Self

import httpx
import stamina
import structlog
from fastapi import Depends, Request

from {{ cookiecutter.package_name }}.core.config import settings

logger = structlog.get_logger(__name__)


class CircuitOpenError(RuntimeError):
    """Raised when the breaker is open and calls fail fast instead of hanging."""


class CircuitBreaker:
    """Minimal async circuit breaker: closed -> open -> half-open."""

    def __init__(self, *, failure_threshold: int, reset_timeout: float) -> None:
        self._threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        async with self._lock:
            if self._opened_at is not None and (time.monotonic() - self._opened_at) < self._reset_timeout:
                raise CircuitOpenError("circuit breaker is open")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        async with self._lock:
            if exc_type is None:
                self._failures = 0
                self._opened_at = None
            else:
                self._failures += 1
                if self._failures >= self._threshold:
                    self._opened_at = time.monotonic()
                    logger.warning("http.circuit_open", failures=self._failures)
        return False


_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


class ResilientHttpClient:
    """Wraps ``httpx.AsyncClient`` with stamina retries and a circuit breaker."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._breaker = CircuitBreaker(
            failure_threshold=settings.http_breaker_failure_threshold,
            reset_timeout=settings.http_breaker_reset_timeout,
        )

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async for attempt in stamina.retry_context(on=_RETRYABLE, attempts=settings.http_retries):
            with attempt:
                async with self._breaker:
                    response = await self._client.request(method, url, **kwargs)
                    if response.status_code >= 500:
                        response.raise_for_status()  # retry + trip the breaker
                return response
        raise CircuitOpenError("retries exhausted")  # unreachable; keeps mypy happy

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def aclose(self) -> None:
        await self._client.aclose()


def create_http_client() -> ResilientHttpClient:
    return ResilientHttpClient(httpx.AsyncClient(timeout=settings.http_timeout))


async def get_http_client(request: Request) -> ResilientHttpClient:
    client: ResilientHttpClient = request.app.state.http_client
    return client


HttpClientDep = Annotated[ResilientHttpClient, Depends(get_http_client)]
