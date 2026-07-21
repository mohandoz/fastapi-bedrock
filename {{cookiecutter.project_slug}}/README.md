# {{ cookiecutter.project_name }}

{{ cookiecutter.project_description }}

Built with FastAPI, SQLModel (SQLAlchemy 2.0 async) and a Domain-Driven Design
layout: each domain is a self-contained vertical slice of models, schemas,
repository, service and router.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Python {{ cookiecutter.python_version }}+ (uv can install it for you)
{%- if cookiecutter.use_docker == "yes" %}
- Docker + Docker Compose (optional, for the containerised stack)
{%- endif %}

## Quick start

```bash
uv sync                     # create the virtualenv and install dependencies
cp .env.example .env        # then edit SECRET_KEY and DATABASE_URL
make run                    # http://127.0.0.1:8000/docs
```

By default the app uses SQLite so it runs with zero external services.
Point `DATABASE_URL` at PostgreSQL for production.

## Project layout

```text
src/{{ cookiecutter.package_name }}/
├── main.py              # app factory, lifespan, middleware
├── core/               # config, database, repository base, logging, security
├── api/                # router aggregation + /health, /ready
└── domains/
{%- if cookiecutter.use_auth == "yes" %}
    ├── auth/           # users, JWT login/refresh, current-user dependencies
{%- endif %}
    └── {{ cookiecutter.first_entity }}/          # models · schemas · repository · service · router
tests/                  # pytest + httpx + polyfactory
migrations/             # async Alembic migrations
```

Requests flow **router → service → repository → database**. Business logic lives
in services and never touches the ORM directly, which keeps domains easy to test.

## Make targets

```text
make install     Install dependencies and pre-commit hooks
make run         Run the dev server with autoreload
make test        Run the test suite with coverage
make lint        Ruff lint + format check
make format      Auto-format and auto-fix
make typecheck   Run mypy (strict)
make check       Run every check
make migrate     Apply database migrations
make revision    Create a migration:  make revision m="message"
{%- if cookiecutter.use_docker == "yes" %}
make docker-up   Build and run the full stack (api + PostgreSQL)
{%- endif %}
```
{% if cookiecutter.use_auth == "yes" %}
## Authentication

JWT bearer authentication using the OAuth2 password flow:

- `POST {{ '{prefix}' }}/auth/register` — create an account
- `POST {{ '{prefix}' }}/auth/login` — exchange credentials for access + refresh tokens
- `POST {{ '{prefix}' }}/auth/refresh` — mint a new access token
- `GET  {{ '{prefix}' }}/auth/me` — the current user

where `{{ '{prefix}' }}` is `{{ '/api/v1' }}` by default. The `{{ cookiecutter.first_entity }}`
routes are protected and require a valid access token.
{% endif %}
## Database migrations

Models are created automatically outside production. For production, use Alembic:

```bash
make revision m="create {{ cookiecutter.first_entity }} table"
make migrate
```
{% if cookiecutter.use_docker == "yes" %}
## Docker

```bash
docker compose up --build
```

This starts the API against a PostgreSQL container and applies migrations on boot.
{% endif %}
## Testing

```bash
make test
```

Tests run against an in-memory SQLite database and exercise the API through an
async HTTP client, so no external services are required.
