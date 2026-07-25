"""Structured logging configuration using structlog.

Routes BOTH application logs (structlog) and standard-library logs (uvicorn,
SQLAlchemy, Alembic) through one rendering pipeline, so the whole process emits
a single consistent stream (JSON in production) carrying the bound request id.
uvicorn's plain-text access log is disabled: ``RequestIDMiddleware`` emits one
structured ``request_completed`` event per request instead.
"""

from __future__ import annotations

import logging
import sys

import structlog
{%- if cookiecutter.use_observability == "yes" %}
from opentelemetry import trace
from structlog.typing import EventDict, Processor, WrappedLogger
{%- else %}
from structlog.typing import Processor
{%- endif %}

from {{ cookiecutter.package_name }}.core.config import settings

_FRAMEWORK_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "sqlalchemy",
    "alembic",
)
{%- if cookiecutter.use_observability == "yes" %}


def _add_trace_context(
    _logger: WrappedLogger, _method_name: str, event_dict: EventDict
) -> EventDict:
    """Stamp the active span's ids so stdout JSON logs can be joined with traces.

    The OTLP log export path carries trace context natively; this covers the
    stdout stream that cluster log collectors scrape. No-op without a recording
    span (e.g. startup logs, or ``OTEL_ENABLED=false``).
    """
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        event_dict["trace_id"] = format(span_context.trace_id, "032x")
        event_dict["span_id"] = format(span_context.span_id, "016x")
    return event_dict
{%- endif %}


def configure_logging() -> None:
    """Configure structlog and the stdlib root logger (idempotent)."""
    level = logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
{%- if cookiecutter.use_observability == "yes" %}
    if settings.otel_enabled:
        shared_processors.append(_add_trace_context)
{%- endif %}

    # structlog loggers hand the event dict to the stdlib handler's formatter.
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer()
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Send framework logs through the single root handler; no duplicate handlers.
    for name in _FRAMEWORK_LOGGERS:
        framework_logger = logging.getLogger(name)
        framework_logger.handlers = []
        framework_logger.propagate = True

    # RequestIDMiddleware logs one structured request_completed event per
    # request; uvicorn's plain-text access line would duplicate it.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers = []
    access_logger.propagate = False


logger = structlog.get_logger()
