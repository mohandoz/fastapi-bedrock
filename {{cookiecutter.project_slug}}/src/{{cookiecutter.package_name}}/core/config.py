"""Application settings, loaded from environment variables and a `.env` file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

{% if cookiecutter.use_rate_limiting == "yes" -%}
from limits import parse as parse_rate_limit
{% endif -%}
{% if cookiecutter.use_auth == "yes" -%}
from pydantic import EmailStr, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
{%- else -%}
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
{%- endif %}
{%- if cookiecutter.use_auth == "yes" %}

DEFAULT_SECRET_KEY = "change-me-to-a-long-random-secret"  # noqa: S105
{%- endif %}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        # File-mounted secrets (Docker secrets, k8s Secret volumes): each file at
        # /run/secrets/<field_name> supplies that setting (see SECURITY.md).
        secrets_dir="/run/secrets" if Path("/run/secrets").is_dir() else None,
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    # JSON-escaped prompt values may legitimately prefer either quote style.
    # fmt: off
    project_name: str = {{ cookiecutter.project_name | tojson }}
    version: str = {{ cookiecutter.version | tojson }}
    description: str = {{ cookiecutter.project_description | tojson }}
    contact_name: str = {{ cookiecutter.author_name | tojson }}
    contact_email: str = {{ cookiecutter.author_email | tojson }}
    # fmt: on
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
    # fmt: off
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/{{ cookiecutter.package_name }}"
    # fmt: on
    db_echo: bool = False
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    db_pool_timeout: int = Field(default=30, gt=0)
    db_pool_recycle: int = Field(default=1800, ge=0)
    # asyncpg connect timeout (seconds); statement/lock timeouts are enforced
    # server-side by Postgres (GUCs, milliseconds).
    db_connect_timeout: float = Field(default=10.0, gt=0)
    db_statement_timeout_ms: int = Field(default=30_000, ge=0)
    db_lock_timeout_ms: int = Field(default=5_000, ge=0)
    # Create tables via SQLModel.metadata.create_all at startup — a local
    # convenience only. Forced off outside local development unless
    # DB_AUTO_CREATE is set explicitly; deployments apply schema with Alembic
    # (see migrations/README).
    db_auto_create: bool = True

    # --- Runtime limits ---
    # Reject request bodies above this many bytes with a 413 (default 2 MiB).
    max_body_size: int = Field(default=2_097_152, ge=1)
    # Cancel non-streaming requests running longer than this (seconds) with a 504.
    request_timeout: float = Field(default=30.0, gt=0)
    # Budget (seconds) for each dependency check inside the /ready probe.
    readiness_check_timeout: float = Field(default=2.0, gt=0)

    # --- CORS / trusted hosts (comma-separated in the environment) ---
    # NoDecode stops pydantic-settings from JSON-decoding these before
    # validation, so `_split_csv` receives the raw comma-separated string.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    allowed_hosts: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])
{%- if cookiecutter.use_auth == "yes" %}

    # --- Security ---
    secret_key: str = DEFAULT_SECRET_KEY
    algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=30, gt=0)
    refresh_token_expire_days: int = Field(default=7, gt=0)
    # Allow unauthenticated signup via POST /auth/register.
    open_registration: bool = True
    # JWT audience/issuer binding — tokens minted here are rejected by any
    # other service that shares the same SECRET_KEY.
    jwt_issuer: str = Field(default="{{ cookiecutter.package_name }}", min_length=1)
    jwt_audience: str = Field(default="{{ cookiecutter.package_name }}", min_length=1)
    # Superuser account created (or promoted) at startup when both are set.
    first_superuser_email: EmailStr | None = None
    first_superuser_password: str | None = None

    # --- Email (password recovery + verification) ---
    # With emails_enabled=false (the default) outbound email is logged instead
    # of sent, so local development never needs an SMTP server.
    emails_enabled: bool = False
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65_535)
    smtp_tls: bool = True  # STARTTLS
    smtp_user: str | None = None
    smtp_password: str | None = None
    # From address for outbound email; falls back to contact_email when unset.
    emails_from_email: EmailStr | None = None
    # Base URL for links embedded in emails; the frontend routes
    # /reset-password and /verify-email receive the token query parameter.
    frontend_url: str = "http://localhost:3000"
    email_token_expire_minutes: int = Field(default=60, gt=0)
    # Block login until the address is verified; registration then sends a
    # verification email.
    require_email_verification: bool = False
{%- endif %}
{%- if cookiecutter.use_rate_limiting == "yes" %}

    # --- Rate limiting ---
    rate_limit: str = "100/minute"
{%- endif %}
{%- if cookiecutter.use_sentry == "yes" %}

    # --- Sentry ---
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = Field(default=0.1, ge=0, le=1)
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
    redis_max_connections: int = Field(default=20, ge=1)
    cache_default_ttl: int = Field(default=300, gt=0)
    redis_stream: str = Field(default="{{ cookiecutter.package_name }}:events", min_length=1)
    redis_consumer_group: str = Field(default="{{ cookiecutter.package_name }}-workers", min_length=1)
    redis_dead_letter_stream: str = Field(
        default="{{ cookiecutter.package_name }}:events:dead-letter",
        min_length=1,
    )
    redis_max_delivery_attempts: int = Field(default=5, ge=1)
    # Approximate hard cap on stream length (XADD MAXLEN ~). The consumer trims
    # processed entries via XTRIM MINID, so this only discards events if
    # consumers lag by more than this many entries.
    redis_stream_maxlen: int = Field(default=1_000_000, ge=1)
    # Replay window for Idempotency-Key response snapshots (seconds).
    idempotency_ttl: int = Field(default=86_400, gt=0)
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
    http_timeout: float = Field(default=10.0, gt=0)
    http_retries: int = Field(default=3, ge=1)
    http_breaker_failure_threshold: int = Field(default=5, ge=1)
    http_breaker_reset_timeout: float = Field(default=30.0, gt=0)
{%- endif %}
{%- if cookiecutter.use_llm_example == "yes" %}

    # --- LLM (Anthropic) ---
    # When unset the SDK falls back to the ANTHROPIC_API_KEY environment
    # variable (or an `ant auth login` profile).
    anthropic_api_key: str | None = None
    anthropic_model: str = Field(default="claude-opus-4-8", min_length=1)
    llm_max_tokens: int = Field(default=16000, ge=1)
    # SDK-level per-request timeout (seconds) and retry budget; see
    # domains/llm/service.py for why these are not core/http.py settings.
    llm_timeout: float = Field(default=60.0, gt=0)
    llm_max_retries: int = Field(default=3, ge=0)
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

    @field_validator("api_v1_prefix")
    @classmethod
    def _validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/") or value == "/" or value.endswith("/"):
            msg = "API_V1_PREFIX must start with '/', contain a path and not end with '/'."
            raise ValueError(msg)
        return value
{%- if cookiecutter.use_rate_limiting == "yes" %}

    @field_validator("rate_limit")
    @classmethod
    def _validate_rate_limit(cls, value: str) -> str:
        try:
            parse_rate_limit(value)
        except ValueError as exc:
            msg = "RATE_LIMIT must be a valid limit such as '100/minute'."
            raise ValueError(msg) from exc
        return value
{%- endif %}

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
        if bool(self.first_superuser_email) != bool(self.first_superuser_password):
            msg = "FIRST_SUPERUSER_EMAIL and FIRST_SUPERUSER_PASSWORD must be set together."
            raise ValueError(msg)
        if self.emails_enabled and not self.smtp_host:
            msg = "EMAILS_ENABLED requires SMTP_HOST to be configured."
            raise ValueError(msg)
        if not self.is_local and self.require_email_verification and not self.emails_enabled:
            msg = "REQUIRE_EMAIL_VERIFICATION requires EMAILS_ENABLED outside local development."
            raise ValueError(msg)
        if not self.is_local and self.emails_enabled and not self.smtp_tls:
            msg = "SMTP_TLS must stay enabled outside local development."
            raise ValueError(msg)
{%- endif %}
        if not self.is_local and "db_auto_create" not in self.model_fields_set:
            self.db_auto_create = False
{%- if cookiecutter.use_redis == "yes" %}
        if self.redis_stream == self.redis_dead_letter_stream:
            msg = "REDIS_DEAD_LETTER_STREAM must differ from REDIS_STREAM."
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
