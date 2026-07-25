"""Live quality evals for the llm domain, built on pydantic-evals.

Two tiers protect the LLM endpoints:

1. ``tests/test_llm.py`` — deterministic unit tests against a faked SDK
   client; they run in normal CI.
2. This module — a small pydantic-evals ``Dataset`` executed against the real
   Anthropic API. It costs money and its scores are stochastic, so it is
   opt-in twice over: the ``evals`` marker is deselected by default (see
   ``addopts`` in pyproject.toml) and every test is skipped unless
   ``ANTHROPIC_API_KEY`` is set.

Run with::

    make evals
    # or: ANTHROPIC_API_KEY=... uv run pytest -m evals --no-cov tests/test_llm_evals.py

Grow this file the way you grow a regression suite: every prompt bug that
reaches production becomes a ``Case``. Deterministic evaluators (like
``MentionsRequiredPhrase`` below) catch hard failures cheaply; the ``LLMJudge``
evaluator grades the fuzzy qualities a string match cannot. pydantic-evals
instruments each run with OpenTelemetry (via ``logfire-api``), so installing
``logfire`` and pointing it at an OTLP endpoint lands eval traces next to the
service's own telemetry.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytest
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, LLMJudge

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.domains.llm.schemas import Completion, CompletionRequest
from {{ cookiecutter.package_name }}.domains.llm.service import LLMService, get_anthropic_client

pytestmark = [
    pytest.mark.evals,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="live LLM evals need ANTHROPIC_API_KEY",
    ),
]


async def complete(prompt: str) -> Completion:
    """The task under evaluation: the same service code the API routes run."""
    service = LLMService(get_anthropic_client())
    response = await service.complete(CompletionRequest(prompt=prompt))
    return response.output


@dataclass
class MentionsRequiredPhrase(Evaluator[str, Completion]):
    """Deterministic gate: the answer mentions the case's ``must_mention`` phrase."""

    def evaluate(self, ctx: EvaluatorContext[str, Completion]) -> bool:
        phrase = (ctx.metadata or {}).get("must_mention", "")
        return bool(phrase) and phrase.lower() in ctx.output.answer.lower()


def build_dataset() -> Dataset[str, Completion]:
    """Built lazily so collecting (and skipping) this module stays free."""
    return Dataset(
        name="llm-completion-quality",
        cases=[
            Case(
                name="capital-of-france",
                inputs="In one short sentence: what is the capital of France?",
                metadata={"must_mention": "Paris"},
            ),
            Case(
                name="sql-vs-nosql",
                inputs="Summarize the main trade-off between SQL and NoSQL databases.",
                metadata={"must_mention": "schema"},
            ),
        ],
        evaluators=[
            MentionsRequiredPhrase(),
            LLMJudge(
                rubric=(
                    "The answer is factually correct, directly addresses the "
                    "question and does not hallucinate."
                ),
                model=f"anthropic:{settings.anthropic_model}",
                include_input=True,
            ),
        ],
    )


async def test_completion_quality() -> None:
    report = await build_dataset().evaluate(complete)
    report.print(include_input=True, include_output=True)

    failures = {
        case.name: [name for name, result in case.assertions.items() if not result.value]
        for case in report.cases
    }
    failures = {name: failed for name, failed in failures.items() if failed}
    assert not failures, f"eval assertions failed: {failures}"
