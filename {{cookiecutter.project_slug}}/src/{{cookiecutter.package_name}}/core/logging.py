"""Structured logging configuration using structlog.

Routes BOTH application logs (structlog) and standard-library logs (uvicorn,
SQLAlchemy, Alembic) through one rendering pipeline, so the whole process emits
a single consistent stream (JSON in production) carrying the bound request id.
"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.typing import Processor

from {{ cookiecutter.package_name }}.core.config import settings

_FRAMEWORK_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "sqlalchemy",
    "alembic",
)


def configure_logging() -> None:
    """Configure structlog and the stdlib root logger (idempotent)."""
    level = logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

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


logger = structlog.get_logger()
