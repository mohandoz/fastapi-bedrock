"""Idempotency-Key support for unsafe endpoints (IETF draft-ietf-httpapi-idempotency-key).

Opt-in per route: build the router with ``route_class=IdempotentAPIRoute`` and
mark the handler with ``@idempotent``. The route class wraps the handler between
routing and execution — FastAPI's documented extension point — so it needs no
middleware and no route-table introspection, and nested ``include_router``
composition cannot break the lookup. Whenever a client sends an
``Idempotency-Key`` header to a marked route, the first request claims the key
in Redis with ``SET NX`` and, if it succeeds (2xx), its response is snapshotted
with a TTL; a retry with the same key and body replays that exact response,
flagged with ``Idempotent-Replayed: true``. Per the draft's error semantics:

- ``409`` while the original request is still in flight;
- ``422`` when the key is reused with a different request body;
- ``400`` when the key is malformed.

Requests without the header — and handlers without the marker — pass through
untouched. A Redis outage fails closed with a ``503``: the client asked for
exactly-once semantics that cannot be honoured without the store.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable, Coroutine
from http.client import responses as _status_phrases
from typing import Any

import redis.asyncio as redis
import structlog
from fastapi import Request, status
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse, Response

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.exceptions import PROBLEM_CONTENT_TYPE, Problem

logger = structlog.get_logger(__name__)

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotent-Replayed"

_MARKER = "_idempotency_opt_in"
_MAX_KEY_LENGTH = 255
# Responses larger than this are not snapshotted (the claim is released instead).
_MAX_SNAPSHOT_BYTES = 1_048_576
# Response headers worth replaying; everything else (request ids, dates,
# security headers) is per-request and re-applied by the middleware stack.
_SNAPSHOT_HEADERS = ("content-type", "location")


def idempotent[F: Callable[..., Any]](func: F) -> F:
    """Mark a route handler as honouring the ``Idempotency-Key`` header.

    Only effective on routers built with ``route_class=IdempotentAPIRoute``.
    Apply *below* the router decorator so the registered endpoint carries the
    marker::

        @router.post("")
        @idempotent
        async def create_item(...): ...
    """
    setattr(func, _MARKER, True)
    return func


class IdempotentAPIRoute(APIRoute):
    """APIRoute whose ``@idempotent`` handlers honour ``Idempotency-Key``.

    Set as ``route_class`` on any router with marked handlers. Unmarked
    handlers — and requests without the header — run the stock handler.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        if not getattr(self.endpoint, _MARKER, False):
            return handler

        async def idempotent_handler(request: Request) -> Response:
            key = request.headers.get(IDEMPOTENCY_KEY_HEADER)
            if key is None:
                return await handler(request)
            return await _dispatch(handler, request, key)

        return idempotent_handler


def _valid_key(key: str) -> bool:
    # The draft treats the key as an opaque string (a UUID is recommended);
    # accept any printable ASCII value of bounded length.
    return 0 < len(key) <= _MAX_KEY_LENGTH and key.isascii() and key.isprintable()


def _problem_response(
    request: Request,
    *,
    status_code: int,
    detail: str,
    problem_type: str = "about:blank",
) -> Response:
    # Built by hand rather than raised: replayed claim verdicts must render as
    # RFC 9457 problem+json without routing through the exception handlers.
    return JSONResponse(
        status_code=status_code,
        content=Problem(
            type=problem_type,
            title=_status_phrases.get(status_code, "Error"),
            status=status_code,
            detail=detail,
            instance=request.url.path,
        ).model_dump(exclude_none=True),
        media_type=PROBLEM_CONTENT_TYPE,
    )


async def _dispatch(
    handler: Callable[[Request], Coroutine[Any, Any, Response]],
    request: Request,
    key: str,
) -> Response:
    """Run ``handler`` under the idempotency protocol for ``key``."""
    if not _valid_key(key):
        return _problem_response(
            request,
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid {IDEMPOTENCY_KEY_HEADER} header: expected a printable"
                f" ASCII value of at most {_MAX_KEY_LENGTH} characters."
            ),
            problem_type="urn:problem-type:idempotency-invalid-key",
        )

    # Fingerprint the body before taking the claim. BodySizeLimitMiddleware's
    # capped receive may raise a 413 here; it propagates to the regular
    # exception handlers with no claim to clean up.
    body = await request.body()
    fingerprint = hashlib.sha256(body).hexdigest()
    # Keys are scoped per method and path: the same key on two endpoints never collides.
    record_key = f"idem:{request.method}:{request.scope['path']}:{key}"
    client: redis.Redis = request.app.state.redis

    try:
        existing = await _claim(request, client, record_key, fingerprint)
    except redis.RedisError:
        logger.warning("idempotency.store_unavailable", record_key=record_key)
        return _problem_response(
            request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Idempotency store unavailable; retry later.",
            problem_type="urn:problem-type:idempotency-unavailable",
        )
    if existing is not None:
        return existing

    # We own the claim: run the request and snapshot the response.
    try:
        response = await handler(request)
    except BaseException:
        # The handler died (error, validation failure or cancellation): release
        # the claim so a retry is processed instead of answered 409 until the TTL.
        await _release(client, record_key)
        raise

    await _snapshot(client, record_key, fingerprint, response)
    return response


async def _claim(
    request: Request, client: redis.Redis, record_key: str, fingerprint: str
) -> Response | None:
    """Claim ``record_key`` or return the response owed to a duplicate.

    ``None`` means the claim is ours and the request should be processed.
    The claim is atomic (``SET NX``) so exactly one request processes a given
    key; the in-flight claim expires after twice the request timeout (the bound
    RequestTimeoutMiddleware enforces), so a crashed worker never wedges a key.
    """
    claim = json.dumps({"state": "in_flight", "fingerprint": fingerprint})
    in_flight_ttl = max(int(settings.request_timeout * 2), 30)
    for _ in range(2):
        if await client.set(record_key, claim, nx=True, ex=in_flight_ttl):
            return None
        raw = await client.get(record_key)
        if raw is None:
            continue  # record expired between SET and GET; try to claim again
        record: dict[str, Any] = json.loads(raw)
        if record["state"] == "in_flight":
            break
        if record["fingerprint"] != fingerprint:
            logger.info("idempotency.fingerprint_mismatch", record_key=record_key)
            return _problem_response(
                request,
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"This {IDEMPOTENCY_KEY_HEADER} was already used"
                    " with a different request body."
                ),
                problem_type="urn:problem-type:idempotency-mismatch",
            )
        logger.info("idempotency.replayed", record_key=record_key)
        headers = dict(record["headers"])
        headers[REPLAYED_HEADER] = "true"
        return Response(
            content=base64.b64decode(record["body"]),
            status_code=record["status"],
            headers=headers,
        )
    logger.info("idempotency.conflict", record_key=record_key)
    return _problem_response(
        request,
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"A request with the same {IDEMPOTENCY_KEY_HEADER} is currently being processed."
        ),
        problem_type="urn:problem-type:idempotency-in-flight",
    )


async def _snapshot(
    client: redis.Redis, record_key: str, fingerprint: str, response: Response
) -> None:
    """Store a replayable snapshot of a 2xx response, or release the claim.

    Only 2xx responses are snapshotted — error responses release the claim so
    the client's retry is processed. Streaming responses carry no rendered
    ``body``; like oversized ones, they are not replayable.
    """
    if 200 <= response.status_code < 300:
        body = getattr(response, "body", None)
        if isinstance(body, bytes) and len(body) <= _MAX_SNAPSHOT_BYTES:
            snapshot = json.dumps(
                {
                    "state": "completed",
                    "fingerprint": fingerprint,
                    "status": response.status_code,
                    "headers": {
                        name: response.headers[name]
                        for name in _SNAPSHOT_HEADERS
                        if name in response.headers
                    },
                    "body": base64.b64encode(body).decode("ascii"),
                }
            )
            try:
                await client.set(record_key, snapshot, ex=settings.idempotency_ttl)
            except redis.RedisError:
                logger.warning("idempotency.snapshot_failed", record_key=record_key)
            return
        logger.warning(
            "idempotency.snapshot_skipped",
            record_key=record_key,
            size=len(body) if isinstance(body, bytes) else None,
        )
    await _release(client, record_key)


async def _release(client: redis.Redis, record_key: str) -> None:
    try:
        await client.delete(record_key)
    except redis.RedisError:
        # The in-flight TTL will clear it; retries 409 until then.
        logger.warning("idempotency.release_failed", record_key=record_key)
