"""Tests for the operational CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
{%- if cookiecutter.use_auth == "yes" %}
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
{%- endif %}
from typer.testing import CliRunner

from {{ cookiecutter.package_name }} import cli
from {{ cookiecutter.package_name }}.core.config import settings
{%- if cookiecutter.use_auth == "yes" %}
from {{ cookiecutter.package_name }}.domains.auth.repository import UserRepository
{%- endif %}

runner = CliRunner()


def test_migrate_defaults_to_upgrade_head(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_alembic(argv: list[str], prog: str) -> None:
        calls.append(list(argv))

    monkeypatch.setattr(cli, "alembic_main", fake_alembic)
    result = runner.invoke(cli.app, ["migrate"])
    assert result.exit_code == 0, result.output
    assert calls == [["upgrade", "head"]]


def test_migrate_passes_arguments_through(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_alembic(argv: list[str], prog: str) -> None:
        calls.append(list(argv))

    monkeypatch.setattr(cli, "alembic_main", fake_alembic)
    result = runner.invoke(cli.app, ["migrate", "downgrade", "-1"])
    assert result.exit_code == 0, result.output
    assert calls == [["downgrade", "-1"]]


def test_seed_runs_seed_script(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "seed.py").write_text("")
    monkeypatch.chdir(tmp_path)
    calls: list[list[str]] = []

    def fake_run(args: list[str], check: bool) -> subprocess.CompletedProcess[bytes]:
        calls.append(args)
        return subprocess.CompletedProcess(args, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = runner.invoke(cli.app, ["seed", "--count", "5"])
    assert result.exit_code == 0, result.output
    assert calls == [[sys.executable, str(Path("scripts", "seed.py")), "--count", "5"]]


def test_seed_fails_outside_project_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli.app, ["seed"])
    assert result.exit_code == 1


def test_openapi_export_writes_schema(tmp_path: Path) -> None:
    output = tmp_path / "contract" / "openapi.json"
    result = runner.invoke(cli.app, ["openapi-export", "--output", str(output)])
    assert result.exit_code == 0, result.output
    schema = json.loads(output.read_text(encoding="utf-8"))
    assert schema["info"]["title"] == settings.project_name
    assert schema["paths"]
{%- if cookiecutter.use_auth == "yes" %}


async def test_create_superuser_creates_promotes_and_noops(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    monkeypatch.setattr(cli, "async_session_factory", session_factory)

    assert await cli._create_superuser("admin@example.com", "supersecret123") == "created"
    assert await cli._create_superuser("admin@example.com", "supersecret123") == "unchanged"

    async with session_factory() as session:
        repository = UserRepository(session)
        user = await repository.get_by_email("admin@example.com")
        assert user is not None
        assert user.is_superuser
        assert user.is_verified
        await repository.update(user, {"is_superuser": False})
        await session.commit()

    assert await cli._create_superuser("admin@example.com", "supersecret123") == "promoted"


def test_createsuperuser_rejects_invalid_email() -> None:
    result = runner.invoke(
        cli.app,
        ["createsuperuser", "--email", "not-an-email", "--password", "supersecret123"],
    )
    assert result.exit_code != 0


def test_createsuperuser_rejects_short_password() -> None:
    result = runner.invoke(
        cli.app,
        ["createsuperuser", "--email", "admin@example.com", "--password", "short"],
    )
    assert result.exit_code != 0
{%- endif %}
