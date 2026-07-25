# syntax=docker/dockerfile:1

# Pin both base images by digest for reproducible builds, e.g.
#   FROM ghcr.io/astral-sh/uv:python{{ cookiecutter.python_version }}-bookworm-slim@sha256:<digest>
# Dependabot's docker ecosystem (.github/dependabot.yml) keeps pinned digests
# current, so the pin costs nothing to maintain.
FROM ghcr.io/astral-sh/uv:python{{ cookiecutter.python_version }}-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# Install the project itself.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev


FROM python:{{ cookiecutter.python_version }}-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="{{ cookiecutter.project_name }}" \
    org.opencontainers.image.description="{{ cookiecutter.project_description }}" \
    org.opencontainers.image.version="{{ cookiecutter.version }}" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.authors="{{ cookiecutter.author_name }} <{{ cookiecutter.author_email }}>"

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Run as a non-root user with a fixed, numeric UID/GID: Kubernetes can only
# verify `runAsNonRoot` against a numeric USER, and deploy/k8s pins these IDs.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app

WORKDIR /app
# Root-owned and read-only to the runtime user: code and venv cannot be
# overwritten by a compromised app process.
COPY --from=builder /app /app

USER 10001:10001
EXPOSE 8000

# TrustedHostMiddleware validates the Host header against ALLOWED_HOSTS, so the
# probe pins `Host: localhost` — keep `localhost` in ALLOWED_HOSTS when you
# narrow it from the default `*` (the k8s probes send the same header).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/api/v1/health', headers={'Host': 'localhost'}))" || exit 1

# Behind a reverse proxy, set FORWARDED_ALLOW_IPS to the proxy address so
# {% if cookiecutter.use_rate_limiting == "yes" %}rate limiting and {% endif %}request logs see real client IPs
# (--proxy-headers matches what `fastapi run` passed). --timeout-graceful-shutdown
# bounds in-flight drain after SIGTERM; keep it below the orchestrator's kill
# grace period (k8s terminationGracePeriodSeconds defaults to 30s).
CMD ["uvicorn", "{{ cookiecutter.package_name }}.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--timeout-graceful-shutdown", "20"]
