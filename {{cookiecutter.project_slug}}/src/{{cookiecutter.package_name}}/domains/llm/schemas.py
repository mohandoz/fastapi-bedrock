"""Request, response and stream-event schemas for the llm domain."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CompletionRequest(BaseModel):
    """Payload accepted by both completion endpoints."""

    prompt: str = Field(
        min_length=1,
        max_length=20_000,
        description="The user prompt sent to the model.",
        examples=["Summarize the key trade-offs between SQL and NoSQL databases."],
    )
    system: str | None = Field(
        default=None,
        max_length=10_000,
        description="Optional system prompt steering the model's behaviour for this call.",
        examples=["You are a terse assistant. Answer in at most three sentences."],
    )


class Completion(BaseModel):
    """Structured-output contract the model must satisfy.

    Passed to the SDK's ``client.messages.parse(..., output_format=Completion)``,
    which constrains generation to this JSON schema and validates the result.
    Keep it flat and constraint-light: structured outputs reject recursive
    schemas and most string/number constraints (the SDK strips unsupported ones
    and re-validates client-side).
    """

    answer: str = Field(description="The answer to the prompt.")
    confidence: Literal["low", "medium", "high"] = Field(
        description="The model's self-assessed confidence in the answer."
    )
    follow_up_questions: list[str] = Field(
        description="Questions the caller could ask next (empty when none apply)."
    )


class CompletionResponse(BaseModel):
    """Envelope returned by ``POST /llm/complete``."""

    output: Completion = Field(description="The schema-validated model output.")
    model: str = Field(
        description="The model that produced the completion.",
        examples=["claude-opus-4-8"],
    )
    input_tokens: int = Field(description="Prompt tokens billed for this completion.")
    output_tokens: int = Field(description="Completion tokens billed for this completion.")


class StreamDelta(BaseModel):
    """``delta`` SSE event: one increment of assistant text."""

    text: str = Field(description="The next chunk of assistant text.")


class StreamDone(BaseModel):
    """``done`` SSE event: emitted once, after the final delta."""

    stop_reason: str | None = Field(
        description="Why the model stopped (e.g. end_turn, max_tokens, refusal)."
    )
    input_tokens: int = Field(description="Prompt tokens billed for this completion.")
    output_tokens: int = Field(description="Completion tokens billed for this completion.")


class StreamError(BaseModel):
    """``error`` SSE event: the upstream call failed after the response started.

    SSE cannot change the HTTP status once streaming has begun, so failures are
    delivered in-band as a terminal event instead of a problem+json response.
    """

    detail: str = Field(description="Human-readable description of the failure.")
