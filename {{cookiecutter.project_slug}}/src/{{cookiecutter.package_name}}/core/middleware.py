"""HTTP middleware: request-id propagation, access logging and security headers.

Both middleware are pure ASGI (no ``BaseHTTPMiddleware``): they spawn no
per-request task, never buffer streaming responses, and run in the request's
own context, so ``structlog.contextvars`` bindings reach every log line
downstream.
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from {{ cookiecutter.package_name }}.core.config import settings

logger = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

_BASE_SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
)
_HSTS_VALUE = "max-age=63072000; includeSubDomains"


def apply_security_headers(headers: MutableHeaders) -> None:
    """Set the baseline security headers, keeping any values already present."""
    for name, value in _BASE_SECURITY_HEADERS:
        if name not in headers:
            headers[name] = value
    if settings.is_production and "Strict-Transport-Security" not in headers:
        headers["Strict-Transport-Security"] = _HSTS_VALUE


class RequestIDMiddleware:
    """Ensure every request has an id, bind log context and emit the access log.

    The id comes from the incoming ``X-Request-ID`` header (or is generated),
    is bound to ``structlog.contextvars`` together with method/path, stashed on
    ``request.state.request_id``, and stamped onto the response by wrapping
    ``send``. Exactly one structured ``request_completed`` event is logged per
    request — including requests that die with an unhandled exception, which
    are recorded as 500s.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = Headers(scope=scope).get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        method: str = scope["method"]
        path: str = scope["path"]
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, method=method, path=path)

        status_code = 500  # unhandled exceptions are rendered as 500s upstream
        started = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "request_completed",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                request_id=request_id,
            )


class SecurityHeadersMiddleware:
    """Attach conservative security headers to every response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                apply_security_headers(MutableHeaders(scope=message))
            await send(message)

        await self.app(scope, receive, send_with_headers)
