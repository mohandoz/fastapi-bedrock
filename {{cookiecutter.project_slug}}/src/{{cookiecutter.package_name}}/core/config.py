"""Application settings, loaded from environment variables and a `.env` file."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
{% if cookiecutter.use_auth == "yes" -%}
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_SECRET_KEY = "change-me-to-a-long-random-secret"  # noqa: S105
{%- else -%}
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
{%- endif %}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    project_name: str = "{{ cookiecutter.project_name }}"
    version: str = "{{ cookiecutter.version }}"
    description: str = "{{ cookiecutter.project_description }}"
    contact_name: str = "{{ cookiecutter.author_name }}"
    contact_email: str = "{{ cookiecutter.author_email }}"
    environment: Literal["local", "staging", "production"] = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    # Serve /docs, /redoc and the OpenAPI schema. Forced off in production
    # unless DOCS_ENABLED is set explicitly.
    docs_enabled: bool = True

    # --- Logging ---
    log_json: bool = True
    log_level: str = "INFO"

    # --- Database (async SQLAlchemy URL) ---
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/{{ cookiecutter.package_name }}"
    )
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800

    # --- CORS / trusted hosts (comma-separated in the environment) ---
    # NoDecode stops pydantic-settings from JSON-decoding these before
    # validation, so `_split_csv` receives the raw comma-separated string.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    allowed_hosts: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])
{%- if cookiecutter.use_auth == "yes" %}

    # --- Security ---
    secret_key: str = DEFAULT_SECRET_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    # Allow unauthenticated signup via POST /auth/register.
    open_registration: bool = True
{%- endif %}
{%- if cookiecutter.use_rate_limiting == "yes" %}

    # --- Rate limiting ---
    rate_limit: str = "100/minute"
{%- endif %}
{%- if cookiecutter.use_sentry == "yes" %}

    # --- Sentry ---
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.1
{%- endif %}
{%- if cookiecutter.use_temporal == "yes" %}

    # --- Temporal ---
    # localhost:7233 for a local `temporal server start-dev`; temporal:7233 in compose.
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "{{ cookiecutter.package_name }}-tq"
{%- endif %}
{%- if cookiecutter.use_redis == "yes" %}

    # --- Redis (cache + streams / pub-sub) ---
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 20
    cache_default_ttl: int = 300
    redis_stream: str = "{{ cookiecutter.package_name }}:events"
    redis_consumer_group: str = "{{ cookiecutter.package_name }}-workers"
    # Approximate hard cap on stream length (XADD MAXLEN ~). The consumer trims
    # processed entries via XTRIM MINID, so this only discards events if
    # consumers lag by more than this many entries.
    redis_stream_maxlen: int = 1_000_000
{%- endif %}
{%- if cookiecutter.use_observability == "yes" %}

    # --- Observability (OpenTelemetry / OTLP) ---
    otel_enabled: bool = False
    otel_service_name: str = "{{ cookiecutter.package_name }}"
    # Base OTLP endpoint; exporters append /v1/traces, /v1/metrics, /v1/logs.
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    # Only http/protobuf is supported (observability.py uses the HTTP exporters);
    # any other value fails validation at boot.
    otel_exporter_otlp_protocol: Literal["http/protobuf"] = "http/protobuf"
{%- endif %}
{%- if cookiecutter.use_http_client == "yes" %}

    # --- Resilient HTTP client (outbound calls) ---
    http_timeout: float = 10.0
    http_retries: int = 3
    http_breaker_failure_threshold: int = 5
    http_breaker_reset_timeout: float = 30.0
{%- endif %}

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_local(self) -> bool:
        return self.environment == "local"

    @field_validator("cors_origins", "allowed_hosts", mode="before")
    @classmethod
    def _split_csv(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _validate_environment_safety(self) -> Settings:
        """Reject configuration that is unsafe outside local development."""
{%- if cookiecutter.use_auth == "yes" %}
        if not self.is_local:
            if self.secret_key == DEFAULT_SECRET_KEY:
                msg = "SECRET_KEY must be overridden outside local development."
                raise ValueError(msg)
            if len(self.secret_key) < 32:
                msg = "SECRET_KEY must be at least 32 characters outside local development."
                raise ValueError(msg)
{%- endif %}
        if self.is_production:
            if self.debug:
                msg = "DEBUG must be disabled in production."
                raise ValueError(msg)
            if not self.allowed_hosts or "*" in self.allowed_hosts:
                msg = "ALLOWED_HOSTS must list explicit hostnames in production."
                raise ValueError(msg)
            if "docs_enabled" not in self.model_fields_set:
                self.docs_enabled = False
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
