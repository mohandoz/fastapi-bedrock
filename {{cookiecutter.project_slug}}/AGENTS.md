# {{ cookiecutter.project_name }} — Agent Guide

Async FastAPI + SQLModel service in a DDD layout. Python {{ cookiecutter.python_version }}, managed with uv
(run everything through `uv run ...` or the make targets below).

## Commands

- `make setup` — deps, `.env`, database, migrations, git hooks (run once)
- `make run` / `make test` / `make lint` / `make format` / `make typecheck` / `make check`
- Tests REQUIRE Docker: pytest boots a throwaway PostgreSQL{% if cookiecutter.use_redis == "yes" %} and Redis{% endif %} via
  testcontainers (`tests/conftest.py`). Never point tests at a real database.
- One test file: `uv run pytest tests/test_{{ cookiecutter.first_entity }}.py -x` (add `-k name` to filter).

## Layering (strict)

- A domain lives in `src/{{ cookiecutter.package_name }}/domains/<name>/`: `router.py` → `service.py` →
  `repository.py`, with `models.py` (tables) and `schemas.py` (I/O shapes).
- Routers NEVER touch the database or session directly — they call the service;
  only repositories execute queries. Business rules belong in services.
- Cross-cutting code lives in `core/` (config, database, exceptions, logging,
  middleware). Domains may import `core`, never another domain's internals.
- Services raise `core.exceptions` types (`NotFoundError`, `ConflictError`, ...);
  handlers render them as RFC 9457 `application/problem+json`.

## Adding a domain

1. `make new-domain name=order` — scaffolds the full slice + tests, mirroring
   `domains/{{ cookiecutter.first_entity }}/`.
2. Register the router in `api/router.py` and the models import in
   `core/database.py:_import_models` (the script prints the exact lines).
3. `make revision m="add orders"` then `make migrate` — migrations live in
   `migrations/versions/` (Alembic autogenerate; review before applying).

## Conventions

- Async everywhere; full type hints (`mypy --strict` must pass); Ruff is the
  only formatter — run `make format` before finishing.
- Every route declares `summary=` and an imperative docstring; schema/model
  fields get `Field(description=..., examples=[...])`. This is not cosmetic:
  it feeds OpenAPI clients{% if cookiecutter.use_mcp == "yes" %}, MCP tool descriptions{% endif %} and `/llms.txt`.
- Log with `structlog.get_logger(__name__)`; never `print`.
{%- if cookiecutter.use_auth == "yes" %}
- Protect routes with `domains.auth.dependencies.get_current_active_user`
  (JWTs are HS256, bound to this service via `iss`/`aud`).
{%- endif %}
{%- if cookiecutter.use_mcp == "yes" %}
- MCP server (`src/{{ cookiecutter.package_name }}/mcp/server.py`, mounted at `/mcp`): expose curated
  tools over services — never raw SQL, never auto-generated from every route.
{%- endif %}

## Gotchas

- `settings` (`core/config.py`) is a cached singleton; tests pin env vars in
  `tests/conftest.py` BEFORE it is imported — follow that pattern.
- Local dev auto-creates tables (`db_auto_create`); staging/production apply
  schema ONLY via Alembic. Keep the shipped initial revision and every later
  model change in sync; `tests/test_migrations.py` rejects schema drift.
