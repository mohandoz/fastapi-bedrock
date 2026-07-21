"""Structured logging configuration using structlog."""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.typing import Processor

from {{ cookiecutter.package_name }}.core.config import settings


def configure_logging() -> None:
    """Configure structlog for the whole process (idempotent)."""
    level = logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger()
