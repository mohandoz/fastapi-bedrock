# FastAPI DDD Cookiecutter

A modern [Cookiecutter](https://cookiecutter.readthedocs.io/) template for
production-ready **FastAPI** services organised with a **Domain-Driven Design**
(vertical-slice) layout.

Every generated project ships fully wired: async database access, a clean
repository/service layering, JWT authentication, tests, linting, typing,
Docker and CI — nothing to bolt on afterwards.

## Stack

| Concern             | Choice                                                             |
| ------------------- | ----------------------------------------------------------------- |
| Language            | Python 3.12+ (defaults to 3.13)                                   |
| Packaging / env     | [uv](https://docs.astral.sh/uv/) (PEP 621 + PEP 735)             |
| Web framework       | [FastAPI](https://fastapi.tiangolo.com/) (`fastapi[standard]`)    |
| Data / ORM          | [SQLModel](https://sqlmodel.tiangolo.com/) on SQLAlchemy 2.0 async|
| Migrations          | [Alembic](https://alembic.sqlalchemy.org/) (async)                |
| Validation / config | Pydantic v2 + `pydantic-settings`                                 |
| Auth                | OAuth2 password flow, JWT access + refresh, Argon2 (`pwdlib`)     |
| Lint + format       | [Ruff](https://docs.astral.sh/ruff/) (replaces black + isort)     |
| Type checking       | [mypy](https://mypy.readthedocs.io/) (strict)                     |
| Tests               | pytest, pytest-asyncio, httpx, polyfactory                        |
| Logging             | [structlog](https://www.structlog.org/) (JSON) + request IDs      |
| Runtime extras      | Docker + compose, GitHub Actions CI, slowapi rate limit, Sentry   |

## Architecture

The generated project follows a **repository → service → router** flow with
each domain as a self-contained vertical slice:

```text
src/<package>/
├── main.py                 # app factory, lifespan, middleware
├── core/                   # cross-cutting infrastructure
│   ├── config.py           # pydantic-settings
│   ├── database.py         # async engine + session dependency
│   ├── repository.py       # generic BaseRepository[Model]
│   ├── security.py         # password hashing + JWT (auth)
│   ├── logging.py          # structlog configuration
│   ├── middleware.py       # request-id middleware
│   └── exceptions.py       # domain errors + handlers
├── api/
│   ├── router.py           # aggregates every domain router under /api/v1
│   └── health.py           # /health and /ready probes
└── domains/
    ├── auth/               # User model, JWT login/refresh, current-user deps
    └── <entity>/           # models · schemas · repository · service · router
```

Business logic never touches the database directly: services depend on thin
repository classes, so a domain is trivial to unit-test and the persistence
layer stays swappable.

## Requirements

- [uv](https://docs.astral.sh/uv/) (recommended), or any Python 3.12+ with
  `cookiecutter` installed.

## Usage

```bash
# with uv (no global install required)
uvx cookiecutter gh:<your-org>/fastapi-ddd-cookiecutter

# or, if cookiecutter is already installed
cookiecutter gh:<your-org>/fastapi-ddd-cookiecutter
```

You will be prompted for the variables below. When generation finishes the
hook initialises a fresh git repository and runs `uv sync` (set the env var
`SKIP_UV_SYNC=1` to opt out).

### Prompts

| Variable              | Description                               | Default               |
| --------------------- | ----------------------------------------- | --------------------- |
| `project_name`        | Human-readable name                       | `FastAPI DDD Service` |
| `project_slug`        | Repo/folder name (derived)                | `fastapi-ddd-service` |
| `package_name`        | Import package (derived)                  | `fastapi_ddd_service` |
| `project_description` | One-line description                      | —                     |
| `author_name`         | Your name                                 | —                     |
| `author_email`        | Your email                                | —                     |
| `version`             | Initial version                           | `0.1.0`               |
| `python_version`      | Target Python                             | `3.13`                |
| `first_entity`        | First domain entity (lowercase snake)     | `item`                |
| `use_auth`            | Include JWT authentication                | `yes`                 |
| `use_docker`          | Include Dockerfile + docker-compose       | `yes`                 |
| `use_github_actions`  | Include CI workflow                       | `yes`                 |
| `use_rate_limiting`   | Include slowapi rate limiting             | `yes`                 |
| `use_sentry`          | Include Sentry error tracking             | `no`                  |

## What you get after generation

```bash
cd <project_slug>
cp .env.example .env        # set SECRET_KEY (required) and DATABASE_URL
make run                    # uv run fastapi dev  ->  http://127.0.0.1:8000/docs
make test                   # pytest with coverage
make lint                   # ruff check + format check
make typecheck              # mypy --strict
make migrate                # alembic upgrade head
```

By default the app runs on SQLite for zero-config local development; the
bundled `docker-compose.yml` switches it to PostgreSQL.

## License

MIT — see [LICENSE](LICENSE).
