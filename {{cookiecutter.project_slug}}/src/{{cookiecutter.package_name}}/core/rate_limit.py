"""Request rate limiting powered by slowapi."""

from __future__ import annotations

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from {{ cookiecutter.package_name }}.core.config import settings

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit])


def add_rate_limiting(app: FastAPI) -> None:
    app.state.limiter = limiter
    # slowapi's handler is typed for RateLimitExceeded rather than Exception.
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)
