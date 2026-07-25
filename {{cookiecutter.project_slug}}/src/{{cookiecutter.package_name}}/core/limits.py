"""Runtime hardening: body-size caps, per-request deadlines and SIGTERM draining."""

from __future__ import annotations

import asyncio
import signal
import threading
from types import FrameType

import structlog
from fastapi import FastAPI, HTTPException, status
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from {{ cookiecutter.package_name }}.core.exceptions import PROBLEM_CONTENT_TYPE, Problem

logger = structlog.get_logger(__name__)


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


class BodySizeLimitMiddleware:
    """Reject request bodies larger than ``max_body_size`` bytes with a 413.

    Pure ASGI: an oversized declared ``Content-Length`` is refused before any
    body bytes are read, and chunked/streamed bodies are hard-capped as they
    arrive so omitting the header cannot bypass the check.
    """

    def __init__(self, app: ASGIApp, max_body_size: int) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _content_length(scope)
        if declared is not None and declared > self.max_body_size:
            logger.warning("request.body_too_large", declared=declared, limit=self.max_body_size)
            # Built by hand: middleware responses bypass the exception handlers,
            # but must still render as RFC 9457 problem+json.
            response = JSONResponse(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                content=Problem(
                    title="Content Too Large",
                    status=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Request body too large.",
                    instance=scope.get("path"),
                ).model_dump(exclude_none=True),
                media_type=PROBLEM_CONTENT_TYPE,
            )
            await response(scope, receive, send)
            return

        received = 0

        async def capped_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_size:
                    logger.warning(
                        "request.body_too_large", received=received, limit=self.max_body_size
                    )
                    # HTTPException so FastAPI's body parsing re-raises it and the
                    # standard handlers render the 413 (any other exception type is
                    # remapped to a 400 "error parsing the body").
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="Request body too large.",
                    )
            return message

        await self.app(scope, capped_receive, send)


class RequestTimeoutMiddleware:
    """Cancel handlers that outlive ``timeout`` seconds and answer with a 504.

    The deadline is disarmed once the response starts, so streaming responses
    (SSE, large downloads) are never killed mid-stream; non-HTTP scopes
    (websockets, lifespan) bypass the middleware entirely.
    """

    def __init__(self, app: ASGIApp, timeout: float) -> None:
        self.app = app
        self.timeout = timeout

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        deadline: asyncio.Timeout | None = None
        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                if deadline is not None:
                    deadline.reschedule(None)  # response underway: stop the clock
            await send(message)

        try:
            async with asyncio.timeout(self.timeout) as deadline:
                await self.app(scope, receive, tracking_send)
        except TimeoutError:
            # Re-raise timeouts that are not ours, and ours if it is already
            # too late to swap in a 504.
            if deadline is None or not deadline.expired() or response_started:
                raise
            logger.warning("request.timeout", path=scope.get("path"), timeout=self.timeout)
            response = JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content=Problem(
                    title="Gateway Timeout",
                    status=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Request timed out.",
                    instance=scope.get("path"),
                ).model_dump(exclude_none=True),
                media_type=PROBLEM_CONTENT_TYPE,
            )
            await response(scope, receive, send)


def install_shutdown_drain(app: FastAPI) -> None:
    """Flip ``app.state.shutting_down`` on SIGTERM so ``/ready`` returns 503.

    Load balancers observe the failing readiness probe and drain the instance
    while uvicorn finishes in-flight requests; the previously installed
    handler (uvicorn's) is chained so graceful shutdown proceeds unchanged.
    Must be called from the lifespan: uvicorn installs its own handlers right
    before startup, and they have to exist to be chained. No-op off the main
    thread (e.g. under the test client), where signal handlers are forbidden.
    """
    app.state.shutting_down = False
    if threading.current_thread() is not threading.main_thread():
        return

    previous = signal.getsignal(signal.SIGTERM)

    def _drain(signum: int, frame: FrameType | None) -> None:
        app.state.shutting_down = True
        logger.info("shutdown.draining", signal=signum)
        if callable(previous):
            previous(signum, frame)

    signal.signal(signal.SIGTERM, _drain)
