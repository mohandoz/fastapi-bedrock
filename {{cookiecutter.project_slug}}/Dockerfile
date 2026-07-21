# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python{{ cookiecutter.python_version }}-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev

# Install the project itself.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev


FROM python:{{ cookiecutter.python_version }}-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Run as a non-root user.
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

WORKDIR /app
COPY --from=builder --chown=app:app /app /app

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')" || exit 1

CMD ["fastapi", "run", "src/{{ cookiecutter.package_name }}/main.py", "--host", "0.0.0.0", "--port", "8000"]
