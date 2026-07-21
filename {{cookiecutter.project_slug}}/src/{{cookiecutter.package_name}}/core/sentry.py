"""Optional Sentry error tracking, enabled when ``SENTRY_DSN`` is set."""

from __future__ import annotations

import sentry_sdk

from {{ cookiecutter.package_name }}.core.config import settings


def init_sentry() -> None:
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=settings.version,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )
