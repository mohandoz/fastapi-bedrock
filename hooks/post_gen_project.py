"""Post-generation hook.

Prunes files for disabled features, initialises a fresh git repository and
(optionally) installs the dependencies with uv.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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
USE_MCP = "{{ cookiecutter.use_mcp }}" == "yes"
USE_LLM_EXAMPLE = "{{ cookiecutter.use_llm_example }}" == "yes"


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
        remove(
            SRC / "domains" / "auth",
            SRC / "core" / "security.py",
            SRC / "core" / "email.py",
            SRC / "email-templates",
            "tests/test_auth.py",
            "docs/recipes/oauth-social-login.md",
        )
    if not USE_DOCKER:
        # dynamicconfig/ is only consumed by the docker-compose Temporal service.
        remove(
            "Dockerfile",
            "docker-compose.yml",
            ".dockerignore",
            "dynamicconfig",
            "deploy",
            ".devcontainer/compose.yml",
        )
    if not USE_CI:
        # Keep dependabot.yml, the PR template and bedrock-mark.svg — only the
        # workflows are Actions-specific.
        remove(".github/workflows")
    if not USE_RATE_LIMITING:
        remove(SRC / "core" / "rate_limit.py")
    if not USE_SENTRY:
        remove(SRC / "core" / "sentry.py")
    if not USE_TEMPORAL:
        remove(SRC / "temporal", "tests/test_temporal.py", "dynamicconfig")
    if not USE_REDIS:
        remove(
            SRC / "core" / "redis.py",
            SRC / "core" / "cache.py",
            SRC / "core" / "lock.py",
            SRC / "core" / "idempotency.py",
            SRC / "events",
            "tests/test_redis.py",
            "tests/test_idempotency.py",
        )
    if not USE_OBSERVABILITY:
        remove(SRC / "core" / "observability.py")
    if not USE_HTTP_CLIENT:
        remove(SRC / "core" / "http.py", "tests/test_http.py")
    if not USE_MCP:
        remove(SRC / "mcp", "tests/test_mcp.py")
    elif not USE_AUTH:
        # The MCP bearer verifier wraps the auth domain's JWTs.
        remove(SRC / "mcp" / "auth.py")
    if not USE_LLM_EXAMPLE:
        remove(
            SRC / "domains" / "llm",
            "tests/test_llm.py",
            "tests/test_llm_evals.py",
        )


def strip_bytecode_caches() -> None:
    """Drop __pycache__ directories copied verbatim from the template source."""
    for cache_dir in list(PROJECT_DIR.rglob("__pycache__")):
        shutil.rmtree(cache_dir, ignore_errors=True)


def warn_missing_lockfile(reason: str) -> None:
    banner = "=" * 72
    print(
        f"\n{banner}\n"
        f"WARNING: {reason}, so uv.lock was NOT generated.\n"
        "Reproducible builds, CI ('uv sync --locked') and the Docker image all\n"
        "require a committed lockfile. Before your first push, run:\n"
        "    uv sync\n"
        "and commit the resulting uv.lock.\n"
        f"{banner}\n",
        file=sys.stderr,
    )


def sync_dependencies() -> None:
    if os.environ.get("SKIP_UV_SYNC") == "1":
        warn_missing_lockfile("SKIP_UV_SYNC=1 skipped dependency installation")
        return
    if shutil.which("uv") is None:
        warn_missing_lockfile(
            "uv is not on PATH (install it from https://docs.astral.sh/uv/)"
        )
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
    # --no-verify: bootstrapping the pre-commit hook environments needs network
    # access and the tree was already ruff-fixed/formatted by sync_dependencies(),
    # so running the hooks here only makes generation slow and flaky. The hooks
    # installed above still guard every later commit.
    # Non-fatal: if git has no configured identity the files simply stay staged.
    run(
        "git",
        "commit",
        "-q",
        "--no-verify",
        "-m",
        "Initial commit from fastapi-bedrock",
    )


def main() -> None:
    prune_disabled_features()
    strip_bytecode_caches()
    run("git", "init", "-q", "-b", "main")
    sync_dependencies()
    initial_commit()
    print(
        "\n"
        "Project '{{ cookiecutter.project_slug }}' created.\n\n"
        "Next steps:\n"
        "  cd {{ cookiecutter.project_slug }}\n"
        "  make setup              # deps, .env{% if cookiecutter.use_auth == 'yes' %} (generated SECRET_KEY){% endif %}, database, migrations, git hooks\n"
        "  make run                # start the dev server\n"
    )


if __name__ == "__main__":
    main()
