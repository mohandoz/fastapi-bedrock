"""Request rate limiting powered by slowapi.

Limits key on the client IP (``get_remote_address``), which is the DIRECT peer
address. Behind a reverse proxy or load balancer every request appears to come
from the proxy, collapsing all users into one shared bucket — run uvicorn with
``--proxy-headers`` and a trusted ``--forwarded-allow-ips`` (or the
``FORWARDED_ALLOW_IPS`` env var) so ``request.client`` reflects the real
client IP. Never trust ``X-Forwarded-For`` from arbitrary peers: that allows
spoofed-header bypass.
{%- if cookiecutter.use_redis == "yes" %}

Counters live in Redis, so limits are shared across workers and replicas and
survive restarts; a Redis outage degrades to per-process in-memory counting
instead of failing closed.
{%- else %}

Counters are in-memory and per-process: with multiple workers the effective
limit multiplies by the worker count, and counters reset on every restart.
{%- endif %}
"""

from __future__ import annotations

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from {{ cookiecutter.package_name }}.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit],
{%- if cookiecutter.use_redis == "yes" %}
    storage_uri=settings.redis_url,
    in_memory_fallback_enabled=True,
{%- endif %}
)


def add_rate_limiting(app: FastAPI) -> None:
    """Register the limiter, its 429 handler and the middleware.

    Call BEFORE the other ``add_middleware`` registrations (Starlette inserts
    each new middleware outermost), so rate-limited responses still traverse
    the CORS, request-ID and security-header middleware.
    """
    app.state.limiter = limiter
    # slowapi's handler is typed for RateLimitExceeded rather than Exception.
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)
