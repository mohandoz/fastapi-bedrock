"""Application settings, loaded from environment variables and a `.env` file."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

{% if cookiecutter.use_auth == "yes" -%}
from pydantic import Field, field_validator, model_validator
{%- else -%}
from pydantic import Field, field_validator
{%- endif %}
from pydantic_settings import BaseSettings, SettingsConfigDict

{% if cookiecutter.use_auth == "yes" %}
DEFAULT_SECRET_KEY = "change-me-to-a-long-random-secret"  # noqa: S105
{% endif %}

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
    cors_origins: list[str] = Field(default_factory=list)
    allowed_hosts: list[str] = Field(default_factory=lambda: ["*"])
{%- if cookiecutter.use_auth == "yes" %}

    # --- Security ---
    secret_key: str = DEFAULT_SECRET_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
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
{%- endif %}
{%- if cookiecutter.use_observability == "yes" %}

    # --- Observability (OpenTelemetry / OTLP) ---
    otel_enabled: bool = False
    otel_service_name: str = "{{ cookiecutter.package_name }}"
    # Base OTLP endpoint; exporters append /v1/traces, /v1/metrics, /v1/logs.
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    otel_exporter_otlp_protocol: Literal["http/protobuf", "grpc"] = "http/protobuf"
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
{%- if cookiecutter.use_auth == "yes" %}

    @model_validator(mode="after")
    def _validate_production_secret(self) -> Settings:
        if self.is_production:
            if self.secret_key == DEFAULT_SECRET_KEY:
                msg = "SECRET_KEY must be set to a strong, unique value in production."
                raise ValueError(msg)
            if len(self.secret_key) < 32:
                msg = "SECRET_KEY must be at least 32 characters in production."
                raise ValueError(msg)
        return self
{%- endif %}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
