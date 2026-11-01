# syntax=docker/dockerfile:1

# Debian trixie is current stable (bookworm is oldstable with a slower
# security-update cadence) and the default base for uv's official images.
#
# Multi-arch digests make the initial build reproducible; generated-project
# Dependabot keeps the selected digest current.
{% if cookiecutter.python_version == "3.12" %}
FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim@sha256:9b269b249ad3de71611f3f4c8cabd38f7786205bbd79f727029a5cfdb072ffd4 AS builder
{% elif cookiecutter.python_version == "3.13" %}
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim@sha256:6e00f3cc376554e74b6d39ce21aafd0b5b86e02eaaf4d0ff0fec1cc1032d2d25 AS builder
{% else %}
FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim@sha256:0e664b12a6be9cd16be1015ec5cc3feebdeb42078ab587389707afbdfab8b10f AS builder
{% endif %}

# UV_MALWARE_CHECK (uv preview) aborts the build if any locked package matches
# an OSV malware advisory.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_MALWARE_CHECK=1 \
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


{% if cookiecutter.python_version == "3.12" %}
FROM python:3.12-slim-trixie@sha256:09f7da3bc104798d0afb40bc08d23ab2da20a76130cec1f2ef170848f5d85217 AS runtime
{% elif cookiecutter.python_version == "3.13" %}
FROM python:3.13-slim-trixie@sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f AS runtime
{% else %}
FROM python:3.14-slim-trixie@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5 AS runtime
{% endif %}

LABEL org.opencontainers.image.title={{ cookiecutter.project_name | tojson }} \
    org.opencontainers.image.description={{ cookiecutter.project_description | tojson }} \
    org.opencontainers.image.version={{ cookiecutter.version | tojson }} \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.authors={{ (cookiecutter.author_name ~ " <" ~ cookiecutter.author_email ~ ">") | tojson }}

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
