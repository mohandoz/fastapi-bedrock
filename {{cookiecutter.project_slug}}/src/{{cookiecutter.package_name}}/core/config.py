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
    environment: Literal["local", "staging", "production"] = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # --- Logging ---
    log_json: bool = True
    log_level: str = "INFO"

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./app.db"
    db_echo: bool = False

    # --- CORS ---
    cors_origins: list[str] = Field(default_factory=list)
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

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value
{%- if cookiecutter.use_auth == "yes" %}

    @model_validator(mode="after")
    def _require_secret_in_production(self) -> Settings:
        if self.is_production and self.secret_key == DEFAULT_SECRET_KEY:
            msg = "SECRET_KEY must be set to a strong, unique value in production."
            raise ValueError(msg)
        return self
{%- endif %}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
