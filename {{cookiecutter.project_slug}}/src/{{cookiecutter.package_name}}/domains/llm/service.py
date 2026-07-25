"""Business logic for the llm domain, on top of the official Anthropic SDK.

Why the SDK is NOT routed through {% if cookiecutter.use_http_client == "yes" %}``core/http.py``'s ``ResilientHttpClient``{% else %}a shared resilient HTTP wrapper{% endif %}:
the SDK owns its transport. It ships retry-with-backoff (``LLM_MAX_RETRIES``,
covering 408/409/429/5xx and connection errors) and per-request timeouts
(``LLM_TIMEOUT``) tuned for the Anthropic API, and its streaming helper manages
the SSE connection itself. Wrapping it in another retry/breaker layer would
double-retry failures and buffer streams. Errors that survive the SDK's own
retries are mapped to ``core.exceptions`` types here, so the API still renders
RFC 9457 problem+json like every other domain.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

import anthropic
import structlog
from anthropic import AsyncAnthropic
from fastapi import status

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.exceptions import AppError
from {{ cookiecutter.package_name }}.domains.llm.schemas import (
    Completion,
    CompletionRequest,
    CompletionResponse,
    StreamDelta,
    StreamDone,
)

logger = structlog.get_logger(__name__)

# Used whenever the request carries no system prompt. Keep it stable: the
# system prompt is the first segment of the prompt-cache prefix, so an
# interpolated timestamp or per-request value here would defeat caching.
DEFAULT_SYSTEM_PROMPT = (
    "You are a careful assistant embedded in the {{ cookiecutter.project_name }} API. "
    "Answer accurately and concisely; say so plainly when you are unsure."
)


class LLMRefusalError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Completion Refused"
    problem_type = "urn:problem-type:llm-refusal"
    detail = "The model declined to answer this prompt."


class LLMUpstreamError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    title = "LLM Upstream Error"
    problem_type = "urn:problem-type:llm-upstream"
    detail = "The Anthropic API is unavailable."


@lru_cache
def get_anthropic_client() -> AsyncAnthropic:
    """Process-wide Anthropic client, built lazily on the first LLM request.

    When ``ANTHROPIC_API_KEY`` is unset in the environment *and* absent from
    ``.env``, the SDK falls back to its own credential resolution (environment
    variables, then an ``ant auth login`` profile). Construction never opens a
    socket, so importing this module is side-effect free. The client is reused
    for the process lifetime; tests replace it via ``dependency_overrides``.
    """
    return AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
    )


def _map_upstream(exc: anthropic.APIConnectionError | anthropic.APIStatusError) -> LLMUpstreamError:
    """Translate SDK failures (post-retry) into the domain's 502 problem type."""
    if isinstance(exc, anthropic.RateLimitError):
        detail = "The Anthropic API rate limit was exceeded; retry later."
    elif isinstance(exc, anthropic.APIConnectionError):
        detail = "Could not reach the Anthropic API."
    else:
        detail = f"The Anthropic API returned status {exc.status_code}."
    logger.warning("llm.upstream_error", error=type(exc).__name__, detail=detail)
    return LLMUpstreamError(detail)


class LLMService:
    """Coordinates prompt -> completion use cases on top of the Anthropic SDK."""

    def __init__(self, client: AsyncAnthropic) -> None:
        self.client = client

    async def complete(self, data: CompletionRequest) -> CompletionResponse:
        """Answer the prompt with output guaranteed to match ``Completion``.

        ``messages.parse`` constrains generation to the schema server-side and
        returns the validated instance on ``parsed_output``.
        """
        try:
            message = await self.client.messages.parse(
                model=settings.anthropic_model,
                max_tokens=settings.llm_max_tokens,
                system=data.system or DEFAULT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": data.prompt}],
                output_format=Completion,
            )
        except (anthropic.APIConnectionError, anthropic.APIStatusError) as exc:
            raise _map_upstream(exc) from exc
        if message.stop_reason == "refusal":
            raise LLMRefusalError
        if message.parsed_output is None:
            # Typically stop_reason == "max_tokens": generation stopped before
            # the JSON document was complete. If this recurs, raise the
            # LLM_MAX_TOKENS setting.
            raise LLMUpstreamError(
                "The completion was cut off before producing valid structured output."
            )
        logger.info(
            "llm.completion",
            model=message.model,
            stop_reason=message.stop_reason,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )
        return CompletionResponse(
            output=message.parsed_output,
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )

    async def stream(self, data: CompletionRequest) -> AsyncIterator[StreamDelta | StreamDone]:
        """Yield assistant-text deltas, then one terminal ``StreamDone``.

        A mid-stream refusal is not an exception here: it surfaces as
        ``stop_reason == "refusal"`` on the ``StreamDone`` event, because by
        then part of the answer has already been delivered.
        """
        try:
            async with self.client.messages.stream(
                model=settings.anthropic_model,
                max_tokens=settings.llm_max_tokens,
                system=data.system or DEFAULT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": data.prompt}],
            ) as message_stream:
                async for text in message_stream.text_stream:
                    yield StreamDelta(text=text)
                final = await message_stream.get_final_message()
        except (anthropic.APIConnectionError, anthropic.APIStatusError) as exc:
            raise _map_upstream(exc) from exc
        logger.info(
            "llm.stream_completed",
            model=final.model,
            stop_reason=final.stop_reason,
            input_tokens=final.usage.input_tokens,
            output_tokens=final.usage.output_tokens,
        )
        yield StreamDone(
            stop_reason=final.stop_reason,
            input_tokens=final.usage.input_tokens,
            output_tokens=final.usage.output_tokens,
        )
