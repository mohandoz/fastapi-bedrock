"""Deterministic tests for the llm domain.

The Anthropic SDK client is replaced with an in-process fake via the
``get_anthropic_client`` dependency, so no network access and no
ANTHROPIC_API_KEY are needed — these tests run in normal CI. They cover the
structured-output mapping, SSE framing, upstream error mapping and the
interaction with the request-timeout middleware, all through the full
middleware stack. Live quality evals live in ``tests/test_llm_evals.py``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import anthropic
import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from {{ cookiecutter.package_name }}.core.config import settings
{%- if cookiecutter.use_auth == "yes" %}
from {{ cookiecutter.package_name }}.domains.auth.dependencies import get_current_active_user
{%- endif %}
from {{ cookiecutter.package_name }}.domains.llm.schemas import Completion
from {{ cookiecutter.package_name }}.domains.llm.service import (
    DEFAULT_SYSTEM_PROMPT,
    get_anthropic_client,
)
from {{ cookiecutter.package_name }}.main import create_app

API = settings.api_v1_prefix

ANTHROPIC_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


# --- Fakes mirroring the slice of the SDK surface the service uses ----------


@dataclass
class FakeUsage:
    input_tokens: int = 7
    output_tokens: int = 11


@dataclass
class FakeMessage:
    """Stands in for the SDK's (Parsed)Message in both endpoints."""

    parsed_output: Completion | None = None
    stop_reason: str | None = "end_turn"
    model: str = "claude-test"
    usage: FakeUsage = field(default_factory=FakeUsage)


class FakeMessageStream:
    """Mimics the async context manager returned by ``messages.stream()``."""

    def __init__(
        self,
        deltas: list[str],
        final: FakeMessage,
        *,
        delay: float = 0.0,
        error: Exception | None = None,
    ) -> None:
        self._deltas = deltas
        self._final = final
        self._delay = delay
        self._error = error

    async def __aenter__(self) -> FakeMessageStream:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    @property
    def text_stream(self) -> AsyncIterator[str]:
        async def iterate() -> AsyncIterator[str]:
            for delta in self._deltas:
                if self._delay:
                    await asyncio.sleep(self._delay)
                yield delta
            if self._error is not None:
                raise self._error

        return iterate()

    async def get_final_message(self) -> FakeMessage:
        return self._final


class FakeMessages:
    """Records every call so tests can assert on the request the service built."""

    def __init__(
        self,
        parse_result: FakeMessage | None = None,
        parse_error: Exception | None = None,
        stream_cm: FakeMessageStream | None = None,
    ) -> None:
        self._parse_result = parse_result
        self._parse_error = parse_error
        self._stream_cm = stream_cm
        self.parse_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> FakeMessage:
        self.parse_calls.append(kwargs)
        if self._parse_error is not None:
            raise self._parse_error
        assert self._parse_result is not None, "test forgot to configure parse_result"
        return self._parse_result

    def stream(self, **kwargs: Any) -> FakeMessageStream:
        self.stream_calls.append(kwargs)
        assert self._stream_cm is not None, "test forgot to configure stream_cm"
        return self._stream_cm


@dataclass
class FakeAnthropic:
    messages: FakeMessages


# --- Helpers -----------------------------------------------------------------


def build_app(fake: FakeAnthropic) -> FastAPI:
    """A full app with only the Anthropic client swapped for the fake."""
    app = create_app()
    app.dependency_overrides[get_anthropic_client] = lambda: fake
{%- if cookiecutter.use_auth == "yes" %}
    # Auth gating is asserted separately (test_llm_routes_require_auth);
    # everything else runs with the user dependency stubbed out.
    app.dependency_overrides[get_current_active_user] = lambda: None
{%- endif %}
{%- if cookiecutter.use_rate_limiting == "yes" %}
    app.state.limiter.enabled = False
{%- endif %}
    return app


def make_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse an SSE body into (event, data) pairs, ignoring comments/pings."""
    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.split("\n\n"):
        event_name = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if data_lines:
            events.append((event_name, json.loads("\n".join(data_lines))))
    return events


# --- POST /llm/complete ------------------------------------------------------


async def test_complete_returns_structured_output() -> None:
    completion = Completion(answer="42", confidence="high", follow_up_questions=["Why 42?"])
    fake = FakeAnthropic(messages=FakeMessages(parse_result=FakeMessage(parsed_output=completion)))

    async with make_client(build_app(fake)) as http:
        response = await http.post(f"{API}/llm/complete", json={"prompt": "meaning of life?"})

    assert response.status_code == 200
    body = response.json()
    assert body["output"] == {
        "answer": "42",
        "confidence": "high",
        "follow_up_questions": ["Why 42?"],
    }
    assert body["model"] == "claude-test"
    assert body["input_tokens"] == 7
    assert body["output_tokens"] == 11

    (call,) = fake.messages.parse_calls
    assert call["model"] == settings.anthropic_model
    assert call["max_tokens"] == settings.llm_max_tokens
    assert call["output_format"] is Completion
    assert call["messages"] == [{"role": "user", "content": "meaning of life?"}]
    assert call["system"] == DEFAULT_SYSTEM_PROMPT  # stable default when omitted


async def test_complete_forwards_system_prompt() -> None:
    completion = Completion(answer="ok", confidence="low", follow_up_questions=[])
    fake = FakeAnthropic(messages=FakeMessages(parse_result=FakeMessage(parsed_output=completion)))

    async with make_client(build_app(fake)) as http:
        response = await http.post(
            f"{API}/llm/complete",
            json={"prompt": "hi", "system": "Answer in French."},
        )

    assert response.status_code == 200
    (call,) = fake.messages.parse_calls
    assert call["system"] == "Answer in French."


async def test_complete_rejects_empty_prompt() -> None:
    fake = FakeAnthropic(messages=FakeMessages())

    async with make_client(build_app(fake)) as http:
        response = await http.post(f"{API}/llm/complete", json={"prompt": ""})

    assert response.status_code == 422
    assert response.json()["type"] == "urn:problem-type:validation-error"
    assert fake.messages.parse_calls == []  # rejected before any upstream call


async def test_complete_refusal_renders_problem() -> None:
    fake = FakeAnthropic(
        messages=FakeMessages(parse_result=FakeMessage(parsed_output=None, stop_reason="refusal"))
    )

    async with make_client(build_app(fake)) as http:
        response = await http.post(f"{API}/llm/complete", json={"prompt": "no thanks"})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "urn:problem-type:llm-refusal"


async def test_complete_truncation_renders_upstream_problem() -> None:
    fake = FakeAnthropic(
        messages=FakeMessages(
            parse_result=FakeMessage(parsed_output=None, stop_reason="max_tokens")
        )
    )

    async with make_client(build_app(fake)) as http:
        response = await http.post(f"{API}/llm/complete", json={"prompt": "hi"})

    assert response.status_code == 502
    assert response.json()["type"] == "urn:problem-type:llm-upstream"


async def test_complete_connection_error_renders_502() -> None:
    fake = FakeAnthropic(
        messages=FakeMessages(parse_error=anthropic.APIConnectionError(request=ANTHROPIC_REQUEST))
    )

    async with make_client(build_app(fake)) as http:
        response = await http.post(f"{API}/llm/complete", json={"prompt": "hi"})

    assert response.status_code == 502
    assert response.json()["type"] == "urn:problem-type:llm-upstream"


async def test_complete_rate_limit_error_renders_502() -> None:
    upstream_response = httpx.Response(429, request=ANTHROPIC_REQUEST)
    fake = FakeAnthropic(
        messages=FakeMessages(
            parse_error=anthropic.RateLimitError(
                "rate limited", response=upstream_response, body=None
            )
        )
    )

    async with make_client(build_app(fake)) as http:
        response = await http.post(f"{API}/llm/complete", json={"prompt": "hi"})

    assert response.status_code == 502
    body = response.json()
    assert body["type"] == "urn:problem-type:llm-upstream"
    assert "rate limit" in body["detail"].lower()


# --- POST /llm/stream --------------------------------------------------------


async def test_stream_emits_deltas_then_done() -> None:
    fake = FakeAnthropic(
        messages=FakeMessages(
            stream_cm=FakeMessageStream(deltas=["Hel", "lo"], final=FakeMessage())
        )
    )

    async with make_client(build_app(fake)) as http:
        response = await http.post(f"{API}/llm/stream", json={"prompt": "hi"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(response.text)
    assert events[0] == ("delta", {"text": "Hel"})
    assert events[1] == ("delta", {"text": "lo"})
    name, payload = events[-1]
    assert name == "done"
    assert payload["stop_reason"] == "end_turn"
    assert payload["input_tokens"] == 7
    assert payload["output_tokens"] == 11

    (call,) = fake.messages.stream_calls
    assert call["model"] == settings.anthropic_model
    assert call["max_tokens"] == settings.llm_max_tokens


async def test_stream_upstream_error_yields_error_event() -> None:
    fake = FakeAnthropic(
        messages=FakeMessages(
            stream_cm=FakeMessageStream(
                deltas=["par"],
                final=FakeMessage(),
                error=anthropic.APIConnectionError(request=ANTHROPIC_REQUEST),
            )
        )
    )

    async with make_client(build_app(fake)) as http:
        response = await http.post(f"{API}/llm/stream", json={"prompt": "hi"})

    # The status is already 200 by the time the upstream call fails, so the
    # failure must arrive in-band as a terminal `error` event.
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert events[0] == ("delta", {"text": "par"})
    name, payload = events[-1]
    assert name == "error"
    assert "anthropic api" in payload["detail"].lower()


async def test_stream_survives_request_timeout_middleware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SSE responses outliving REQUEST_TIMEOUT must not be killed mid-stream.

    RequestTimeoutMiddleware disarms its deadline once the response starts;
    this pins that behaviour for the streaming endpoint: three deltas paced at
    0.15s against a 0.2s budget stream to completion.
    """
    monkeypatch.setattr(settings, "request_timeout", 0.2)
    fake = FakeAnthropic(
        messages=FakeMessages(
            stream_cm=FakeMessageStream(deltas=["a", "b", "c"], final=FakeMessage(), delay=0.15)
        )
    )

    async with make_client(build_app(fake)) as http:
        response = await http.post(f"{API}/llm/stream", json={"prompt": "hi"})

    assert response.status_code == 200
    events = parse_sse(response.text)
    assert [payload["text"] for name, payload in events if name == "delta"] == ["a", "b", "c"]
    assert events[-1][0] == "done"
{%- if cookiecutter.use_auth == "yes" %}


# --- Auth gating -------------------------------------------------------------


async def test_llm_routes_require_auth() -> None:
    """Without a bearer token both endpoints answer 401 before any upstream call."""
    app = create_app()  # no overrides: the real auth dependency runs
{%- if cookiecutter.use_rate_limiting == "yes" %}
    app.state.limiter.enabled = False
{%- endif %}
    async with make_client(app) as http:
        for path in ("/llm/complete", "/llm/stream"):
            response = await http.post(f"{API}{path}", json={"prompt": "hi"})
            assert response.status_code == 401, path
{%- endif %}
