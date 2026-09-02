"""HTTP routes for the llm domain."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

import structlog
from anthropic import AsyncAnthropic
{% if cookiecutter.use_rate_limiting == "yes" -%}
from fastapi import APIRouter, Depends, Request
{%- else -%}
from fastapi import APIRouter, Depends
{%- endif %}
from fastapi.sse import EventSourceResponse, ServerSentEvent

{% if cookiecutter.use_rate_limiting == "yes" -%}
from {{ cookiecutter.package_name }}.core.rate_limit import limiter
{%- endif %}
{% if cookiecutter.use_auth == "yes" -%}
from {{ cookiecutter.package_name }}.domains.auth.dependencies import get_current_active_user
{% endif -%}
from {{ cookiecutter.package_name }}.domains.llm.schemas import (
    CompletionRequest,
    CompletionResponse,
    StreamDelta,
    StreamError,
)
from {{ cookiecutter.package_name }}.domains.llm.service import (
    LLMService,
    LLMUpstreamError,
    get_anthropic_client,
)

logger = structlog.get_logger(__name__)


def get_llm_service(
    client: Annotated[AsyncAnthropic, Depends(get_anthropic_client)],
) -> LLMService:
    return LLMService(client)


ServiceDep = Annotated[LLMService, Depends(get_llm_service)]

router = APIRouter(
    prefix="/llm",
    tags=["llm"],
{%- if cookiecutter.use_auth == "yes" %}
    # Completions are metered upstream — never serve them unauthenticated.
    dependencies=[Depends(get_current_active_user)],
{%- endif %}
)


@router.post(
    "/complete",
    summary="Create a structured completion",
    response_description="The schema-validated completion plus token usage.",
)
{%- if cookiecutter.use_rate_limiting == "yes" %}
@limiter.limit("20/minute")
async def create_completion(
    request: Request,
    data: CompletionRequest,
    service: ServiceDep,
) -> CompletionResponse:
{%- else %}
async def create_completion(data: CompletionRequest, service: ServiceDep) -> CompletionResponse:
{%- endif %}
    """Answer the prompt with output guaranteed to match the Completion schema."""
    return await service.complete(data)


@router.post(
    "/stream",
    response_class=EventSourceResponse,
    summary="Stream a completion over SSE",
    response_description="A text/event-stream of delta events, closed by one done event.",
)
{%- if cookiecutter.use_rate_limiting == "yes" %}
@limiter.limit("20/minute")
async def stream_completion(
    request: Request,
    data: CompletionRequest,
    service: ServiceDep,
) -> AsyncIterator[ServerSentEvent]:
{%- else %}
async def stream_completion(
    data: CompletionRequest, service: ServiceDep
) -> AsyncIterator[ServerSentEvent]:
{%- endif %}
    """Stream the completion as Server-Sent Events.

    Emits `delta` events carrying text increments, then one `done` event with
    the stop reason and token usage. Because SSE cannot change the HTTP status
    once the response has started, upstream failures after that point are
    delivered as a terminal `error` event instead of a problem+json body.
    """
    try:
        async for event in service.stream(data):
            if isinstance(event, StreamDelta):
                yield ServerSentEvent(event="delta", data=event)
            else:
                yield ServerSentEvent(event="done", data=event)
    except LLMUpstreamError as exc:
        logger.warning("llm.stream_failed", detail=exc.detail)
        yield ServerSentEvent(event="error", data=StreamError(detail=exc.detail))
