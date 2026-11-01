"""Tests for settings parsing, covering the comma-separated env formats."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from {{ cookiecutter.package_name }}.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"


def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every Settings-mapped variable so only the dotenv file is read."""
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)


def test_env_example_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    """The documented `cp .env.example .env` flow must produce valid settings."""
    _clear_settings_env(monkeypatch)
    settings = Settings(_env_file=ENV_EXAMPLE)
    assert settings.environment == "local"
    assert settings.cors_origins == ["http://localhost:3000"]
    assert settings.allowed_hosts == ["*"]


def test_csv_env_vars_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Comma-separated process env values (the docker-compose path) parse into lists."""
    monkeypatch.setenv("CORS_ORIGINS", "http://a.example, http://b.example")
    monkeypatch.setenv("ALLOWED_HOSTS", "api.example.com")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://a.example", "http://b.example"]
    assert settings.allowed_hosts == ["api.example.com"]


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MAX_BODY_SIZE", "0"),
        ("REQUEST_TIMEOUT", "0"),
        ("READINESS_CHECK_TIMEOUT", "-1"),
        ("DB_POOL_SIZE", "0"),
    ],
)
def test_invalid_runtime_limits_fail_fast(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_api_prefix_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_V1_PREFIX", "api/v1/")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
{%- if cookiecutter.use_rate_limiting == "yes" %}


def test_invalid_rate_limit_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT", "unlimited")
    with pytest.raises(ValidationError, match="RATE_LIMIT"):
        Settings(_env_file=None)
{%- endif %}
{%- if cookiecutter.use_redis == "yes" %}


def test_dead_letter_stream_must_be_distinct() -> None:
    with pytest.raises(ValidationError, match="REDIS_DEAD_LETTER_STREAM"):
        Settings(
            _env_file=None,
            redis_stream="events",
            redis_dead_letter_stream="events",
        )
{%- endif %}
{%- if cookiecutter.use_auth == "yes" %}


def test_example_kubernetes_secret_is_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY must be overridden"):
        Settings(
            _env_file=None,
            environment="production",
            allowed_hosts=["api.example.com"],
            secret_key="change-me-to-a-long-random-secret",
        )


def test_production_verification_requires_email_delivery() -> None:
    with pytest.raises(ValidationError, match="REQUIRE_EMAIL_VERIFICATION"):
        Settings(
            _env_file=None,
            environment="production",
            allowed_hosts=["api.example.com"],
            secret_key="production-test-secret-that-is-long-enough",
            require_email_verification=True,
            emails_enabled=False,
        )
{%- endif %}
