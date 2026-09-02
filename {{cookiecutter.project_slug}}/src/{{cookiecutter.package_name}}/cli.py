"""Operational command-line interface for the generated service.

Registered as the ``{{ cookiecutter.project_slug }}`` console script. Run it
from the project root — ``migrate`` and ``seed`` resolve ``alembic.ini`` and
``scripts/seed.py`` relative to the working directory::

    uv run {{ cookiecutter.project_slug }} --help
"""

from __future__ import annotations

{% if cookiecutter.use_auth == "yes" -%}
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Literal

import typer
from alembic.config import main as alembic_main
from pydantic import EmailStr, TypeAdapter, ValidationError

from {{ cookiecutter.package_name }}.core.config import settings
from {{ cookiecutter.package_name }}.core.database import async_session_factory, dispose_db
from {{ cookiecutter.package_name }}.core.security import hash_password
from {{ cookiecutter.package_name }}.domains.auth.models import User
from {{ cookiecutter.package_name }}.domains.auth.repository import UserRepository
{%- else -%}
import json
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from alembic.config import main as alembic_main

from {{ cookiecutter.package_name }}.core.config import settings
{%- endif %}

app = typer.Typer(
    help=f"Operational commands for {settings.project_name}.",
    no_args_is_help=True,
)
{%- if cookiecutter.use_auth == "yes" %}


async def _create_superuser(
    email: str, password: str
) -> Literal["created", "promoted", "unchanged"]:
    """Create ``email`` as a verified superuser, or promote the existing account."""
    async with async_session_factory() as session:
        repository = UserRepository(session)
        user = await repository.get_by_email(email)
        if user is None:
            # The blocking Argon2 hash is fine here: the CLI runs a single task.
            await repository.add(
                User(
                    email=email,
                    hashed_password=hash_password(password),
                    is_superuser=True,
                    is_verified=True,
                )
            )
            await session.commit()
            return "created"
        if not user.is_superuser:
            await repository.update(user, {"is_superuser": True})
            await session.commit()
            return "promoted"
        return "unchanged"


@app.command()
def createsuperuser(
    email: Annotated[str, typer.Option(prompt=True, help="Email address for the account.")],
    password: Annotated[
        str,
        typer.Option(
            prompt=True,
            hide_input=True,
            confirmation_prompt=True,
            help="Password for the account (prompted for when omitted).",
        ),
    ],
) -> None:
    """Create a verified superuser, or promote an existing user.

    The password of an existing account is never changed.
    """
    try:
        address = TypeAdapter(EmailStr).validate_python(email).lower()
    except ValidationError as exc:
        raise typer.BadParameter("not a valid email address.", param_hint="--email") from exc
    if not 8 <= len(password) <= 128:  # mirrors the UserCreate schema constraint
        raise typer.BadParameter("must be 8-128 characters.", param_hint="--password")

    async def run() -> Literal["created", "promoted", "unchanged"]:
        try:
            return await _create_superuser(address, password)
        finally:
            await dispose_db()

    outcome = asyncio.run(run())
    messages = {
        "created": f"Superuser {address} created.",
        "promoted": f"Existing user {address} promoted to superuser.",
        "unchanged": f"{address} is already a superuser - nothing to do.",
    }
    typer.echo(messages[outcome])
{%- endif %}


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def migrate(ctx: typer.Context) -> None:
    """Run Alembic with the given arguments (defaults to ``upgrade head``).

    Examples: ``migrate``, ``migrate downgrade -1``, ``migrate current``.
    """
    alembic_main(argv=list(ctx.args) or ["upgrade", "head"], prog="alembic")


@app.command()
def seed(
    count: Annotated[int, typer.Option(min=1, help="Rows to create.")] = 25,
) -> None:
    """Seed the local database with demo data (runs ``scripts/seed.py``)."""
    script = Path("scripts") / "seed.py"
    if not script.is_file():
        typer.echo(f"{script} not found - run from the project root.", err=True)
        raise typer.Exit(code=1)
    # Not untrusted input: our own interpreter running a repository script.
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(script), "--count", str(count)], check=False
    )
    raise typer.Exit(code=result.returncode)


@app.command("openapi-export")
def openapi_export(
    output: Annotated[Path, typer.Option("--output", "-o", help="Destination file.")] = Path(
        "openapi.json"
    ),
) -> None:
    """Write the OpenAPI schema to a file without starting the server."""
    from {{ cookiecutter.package_name }}.main import create_app  # deferred: imports the full app

    schema = create_app().openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Wrote {output}")


if __name__ == "__main__":
    app()
