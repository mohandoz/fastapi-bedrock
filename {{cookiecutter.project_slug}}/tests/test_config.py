"""Tests for settings parsing, covering the comma-separated env formats."""

from __future__ import annotations

from pathlib import Path

import pytest

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
