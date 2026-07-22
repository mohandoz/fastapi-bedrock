"""Post-generation hook.

Prunes files for disabled features, initialises a fresh git repository and
(optionally) installs the dependencies with uv.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

PROJECT_DIR = Path.cwd()
PACKAGE = "{{ cookiecutter.package_name }}"
SRC = Path("src") / PACKAGE

USE_AUTH = "{{ cookiecutter.use_auth }}" == "yes"
USE_DOCKER = "{{ cookiecutter.use_docker }}" == "yes"
USE_CI = "{{ cookiecutter.use_github_actions }}" == "yes"
USE_RATE_LIMITING = "{{ cookiecutter.use_rate_limiting }}" == "yes"
USE_SENTRY = "{{ cookiecutter.use_sentry }}" == "yes"
USE_TEMPORAL = "{{ cookiecutter.use_temporal }}" == "yes"
USE_REDIS = "{{ cookiecutter.use_redis }}" == "yes"
USE_OBSERVABILITY = "{{ cookiecutter.use_observability }}" == "yes"
USE_HTTP_CLIENT = "{{ cookiecutter.use_http_client }}" == "yes"


def remove(*relative_paths: str | Path) -> None:
    for relative in relative_paths:
        target = PROJECT_DIR / relative
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink()


def run(*command: str) -> bool:
    try:
        subprocess.run(command, check=True, cwd=PROJECT_DIR)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def prune_disabled_features() -> None:
    if not USE_AUTH:
        remove(SRC / "domains" / "auth", SRC / "core" / "security.py", "tests/test_auth.py")
    if not USE_DOCKER:
        remove("Dockerfile", "docker-compose.yml", ".dockerignore")
    if not USE_CI:
        remove(".github")
    if not USE_RATE_LIMITING:
        remove(SRC / "core" / "rate_limit.py")
    if not USE_SENTRY:
        remove(SRC / "core" / "sentry.py")
    if not USE_TEMPORAL:
        remove(SRC / "temporal", "tests/test_temporal.py", "dynamicconfig")
    if not USE_REDIS:
        remove(SRC / "core" / "redis.py", SRC / "core" / "cache.py", SRC / "events", "tests/test_redis.py")
    if not USE_OBSERVABILITY:
        remove(SRC / "core" / "observability.py")
    if not USE_HTTP_CLIENT:
        remove(SRC / "core" / "http.py", "tests/test_http.py")


def sync_dependencies() -> None:
    if os.environ.get("SKIP_UV_SYNC") == "1":
        return
    if shutil.which("uv") is None:
        print("uv not found on PATH. Install it from https://docs.astral.sh/uv/ and run 'uv sync'.")
        return
    print("Installing dependencies with 'uv sync' (this may take a moment)...")
    if not run("uv", "sync"):
        return
    # Normalise imports/formatting so the first commit is lint-clean.
    run("uv", "run", "ruff", "check", "--fix", "--quiet", ".")
    run("uv", "run", "ruff", "format", "--quiet", ".")
    run("uv", "run", "pre-commit", "install")


def initial_commit() -> None:
    run("git", "add", "-A")
    # Non-fatal: if git has no configured identity the files simply stay staged.
    run("git", "commit", "-q", "-m", "Initial commit from fastapi-bedrock")


def main() -> None:
    prune_disabled_features()
    run("git", "init", "-q", "-b", "main")
    sync_dependencies()
    initial_commit()
    print(
        "\n"
        "Project '{{ cookiecutter.project_slug }}' created.\n\n"
        "Next steps:\n"
        "  cd {{ cookiecutter.project_slug }}\n"
        "  uv sync                 # if it was skipped above\n"
        "  cp .env.example .env    # then edit SECRET_KEY and DATABASE_URL\n"
        "  make run                # start the dev server\n"
    )


if __name__ == "__main__":
    main()
