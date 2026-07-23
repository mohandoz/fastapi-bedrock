"""A resilient async HTTP client: timeouts + retries + circuit breakers.

Hand-written and typed (no sidecar, no magic) — the outbound-call counterpart to
the retries Temporal gives inbound work. Injected via ``HttpClientDep``.

Retries are only automatic for idempotent methods: a timed-out POST may already
have been processed upstream, so replaying it risks duplicate side effects.
Each target host gets its own circuit breaker, so one flaky upstream cannot
open the circuit for every other healthy one.
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

_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})


class CircuitOpenError(RuntimeError):
    """Raised when the breaker is open and calls fail fast instead of hanging."""


class CircuitBreaker:
    """Minimal async circuit breaker: closed -> open -> half-open (one probe)."""

    def __init__(self, *, failure_threshold: int, reset_timeout: float) -> None:
        self._threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._failures = 0
        self._opened_at: float | None = None
        self._probing = False
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        async with self._lock:
            if self._opened_at is not None:
                if (time.monotonic() - self._opened_at) < self._reset_timeout:
                    raise CircuitOpenError("circuit breaker is open")
                if self._probing:
                    # Half-open: admit a single probe; everyone else fails fast
                    # instead of slamming the recovering upstream at once.
                    raise CircuitOpenError("circuit breaker is half-open")
                self._probing = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        async with self._lock:
            self._probing = False
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
    """Wraps ``httpx.AsyncClient`` with stamina retries and per-host breakers."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._breakers: dict[str, CircuitBreaker] = {}

    def _breaker_for(self, url: str) -> CircuitBreaker:
        host = httpx.URL(url).host
        breaker = self._breakers.get(host)
        if breaker is None:
            breaker = self._breakers[host] = CircuitBreaker(
                failure_threshold=settings.http_breaker_failure_threshold,
                reset_timeout=settings.http_breaker_reset_timeout,
            )
        return breaker

    async def request(
        self, method: str, url: str, *, retry: bool | None = None, **kwargs: Any
    ) -> httpx.Response:
        """Send a request through the host's breaker, retrying transient failures.

        By default only idempotent methods are retried; pass ``retry=True`` to
        opt a non-idempotent call in (e.g. when the upstream honours an
        ``Idempotency-Key``), or ``retry=False`` to disable retries entirely.
        """
        breaker = self._breaker_for(url)
        should_retry = retry if retry is not None else method.upper() in _IDEMPOTENT_METHODS
        attempts = settings.http_retries if should_retry else 1
        async for attempt in stamina.retry_context(on=_RETRYABLE, attempts=attempts):
            with attempt:
                async with breaker:
                    response = await self._client.request(method, url, **kwargs)
                    if response.status_code >= 500:
                        response.raise_for_status()  # retry + trip the breaker
                return response
        raise CircuitOpenError("retries exhausted")  # unreachable; keeps mypy happy

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, *, retry: bool = False, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, retry=retry, **kwargs)

    async def aclose(self) -> None:
        await self._client.aclose()


def create_http_client() -> ResilientHttpClient:
    return ResilientHttpClient(httpx.AsyncClient(timeout=settings.http_timeout))


async def get_http_client(request: Request) -> ResilientHttpClient:
    client: ResilientHttpClient = request.app.state.http_client
    return client


HttpClientDep = Annotated[ResilientHttpClient, Depends(get_http_client)]
