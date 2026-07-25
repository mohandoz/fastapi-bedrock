"""Application exceptions and the handlers that render them as RFC 9457 problems.

Every error response — domain ``AppError``s, ``HTTPException``s, request
validation failures and unhandled 500s — is an ``application/problem+json``
document (RFC 9457) carrying ``type``/``title``/``status``/``detail``/
``instance``, so machine clients can dispatch on the stable ``type`` member
instead of parsing prose.
"""

from __future__ import annotations

from collections.abc import Mapping
from http.client import responses as _status_phrases
from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.utils import is_body_allowed_for_status_code
from pydantic import BaseModel
{%- if cookiecutter.use_rate_limiting == "yes" %}
from slowapi.errors import RateLimitExceeded
{%- endif %}
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from {{ cookiecutter.package_name }}.core.middleware import (
    REQUEST_ID_HEADER,
    apply_security_headers,
)

logger = structlog.get_logger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"


class Problem(BaseModel):
    """RFC 9457 problem-details document: the shape of every error response."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    # Extension member: the failing fields on validation errors.
    errors: list[dict[str, Any]] | None = None


class ProblemResponse(JSONResponse):
    media_type = PROBLEM_CONTENT_TYPE


def problem_response(description: str) -> dict[str, Any]:
    """Build an OpenAPI ``responses`` entry documenting a problem+json error."""
    return {
        "description": description,
        "content": {PROBLEM_CONTENT_TYPE: {"schema": Problem.model_json_schema()}},
    }


# Default error documentation for every route; passed to ``include_router`` in
# ``create_app()``. Declaring 422 here also replaces FastAPI's default
# ``HTTPValidationError`` response model in the schema.
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: problem_response("Validation error"),
    status.HTTP_500_INTERNAL_SERVER_ERROR: problem_response("Internal server error"),
}


class AppError(Exception):
    """Base class for expected, HTTP-mappable domain errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    title: str = "Internal Server Error"
    problem_type: str = "urn:problem-type:internal-error"
    detail: str = "Internal server error"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    title = "Not Found"
    problem_type = "urn:problem-type:not-found"
    detail = "Resource not found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    title = "Conflict"
    problem_type = "urn:problem-type:conflict"
    detail = "Resource already exists"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    title = "Unauthorized"
    problem_type = "urn:problem-type:unauthorized"
    detail = "Not authenticated"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    title = "Forbidden"
    problem_type = "urn:problem-type:forbidden"
    detail = "Operation not permitted"


def _problem(
    request: Request,
    *,
    status_code: int,
    title: str,
    detail: str | None = None,
    problem_type: str = "about:blank",
    errors: list[dict[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> ProblemResponse:
    document = Problem(
        type=problem_type,
        title=title,
        status=status_code,
        detail=detail,
        instance=request.url.path,
        errors=errors,
    )
    return ProblemResponse(
        status_code=status_code,
        content=document.model_dump(exclude_none=True),
        headers=headers,
    )


def add_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> ProblemResponse:
        headers = (
            {"WWW-Authenticate": "Bearer"}
            if exc.status_code == status.HTTP_401_UNAUTHORIZED
            else None
        )
        return _problem(
            request,
            status_code=exc.status_code,
            title=exc.title,
            detail=exc.detail,
            problem_type=exc.problem_type,
            headers=headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> Response:
        # Framework-raised errors: routing 404s, dependency 401s, capped-body 413s...
        if not is_body_allowed_for_status_code(exc.status_code):
            return Response(status_code=exc.status_code, headers=exc.headers)
        return _problem(
            request,
            status_code=exc.status_code,
            title=_status_phrases.get(exc.status_code, "Error"),
            detail=str(exc.detail),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> ProblemResponse:
        return _problem(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="Validation Error",
            detail="Request validation failed.",
            problem_type="urn:problem-type:validation-error",
            errors=jsonable_encoder(exc.errors()),
        )
{%- if cookiecutter.use_rate_limiting == "yes" %}

    @app.exception_handler(RateLimitExceeded)
    async def _handle_rate_limit(request: Request, exc: RateLimitExceeded) -> Response:
        response = _problem(
            request,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            title="Too Many Requests",
            detail=f"Rate limit exceeded: {exc.detail}.",
            problem_type="urn:problem-type:rate-limited",
        )
        # Mirror slowapi's bundled handler: stamp Retry-After / X-RateLimit-*
        # onto the response when the limiter has header injection enabled.
        limiter = request.app.state.limiter
        limited: Response = limiter._inject_headers(response, request.state.view_rate_limit)
        return limited
{%- endif %}

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, _exc: Exception) -> ProblemResponse:
        # Logged through structlog (with the bound request id), never leaked to the client.
        logger.exception("unhandled_error")
        response = _problem(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal Server Error",
            detail="Internal server error",
            problem_type="urn:problem-type:internal-error",
        )
        # Starlette renders this handler in the OUTERMOST error middleware, so
        # the response bypasses RequestIDMiddleware and SecurityHeadersMiddleware
        # — reapply their headers here.
        request_id = getattr(request.state, "request_id", None)
        if request_id is not None:
            response.headers[REQUEST_ID_HEADER] = request_id
        apply_security_headers(response.headers)
        return response
