# fastapi-bedrock

<img src="assets/logo.svg" alt="fastapi-bedrock" width="360">

*The solid, layered foundation you build your FastAPI service on.*

A [Cookiecutter](https://cookiecutter.readthedocs.io/) template for
production-ready **FastAPI** services organised with a **Domain-Driven Design**
(vertical-slice) layout. Every generated project ships fully wired: async
database access, a clean repository/service layering, JWT authentication,
tests against a real PostgreSQL, linting, strict typing, Docker and CI —
nothing to bolt on afterwards.

!!! note "Not related to Amazon Bedrock"
    *Bedrock* here means what it says on the tin — the solid layer of rock you
    build on. This project is a template for FastAPI backend services and has
    no connection to AWS's Amazon Bedrock LLM platform.

## Why this template

- **Backend-first.** No frontend to delete. The output is an API service the
  way platform and microservice teams actually deploy them.
- **Composable.** Nine `use_*` flags add or remove whole modules — auth,
  Docker, CI, rate limiting, Sentry, Temporal, Redis, OpenTelemetry, an
  outbound HTTP client — and every combination is exercised in the template's
  own CI matrix. See the [options matrix](options.md).
- **Opinionated where it pays.** Repository → service → router layering,
  RFC 9457 `problem+json` errors, refresh-token rotation with reuse detection,
  a transactional outbox for events, structlog JSON logging with request IDs.
  See [architecture](architecture.md).
- **Updatable.** Generate with [cruft](https://cruft.github.io/cruft/) and
  later pull template improvements into your project as a reviewable diff.
  See [upgrading](upgrading.md).
- **Tested like production.** pytest + testcontainers run the suite against a
  real PostgreSQL — no SQLite stand-in — and `mypy --strict` covers `src`
  *and* `tests`.

## The stack

| Concern             | Choice                                                        |
| ------------------- | ------------------------------------------------------------- |
| Language            | Python 3.12 / 3.13 / 3.14                                     |
| Packaging / env     | [uv](https://docs.astral.sh/uv/) (PEP 621 + PEP 735)          |
| Web framework       | [FastAPI](https://fastapi.tiangolo.com/)                      |
| Data / ORM          | [SQLModel](https://sqlmodel.tiangolo.com/) on SQLAlchemy 2.0 async — PostgreSQL / asyncpg |
| Migrations          | [Alembic](https://alembic.sqlalchemy.org/) (async)            |
| Validation / config | Pydantic v2 + `pydantic-settings`                             |
| Auth                | OAuth2 password flow, JWT access + refresh, Argon2 (`pwdlib`) |
| Lint + format       | [Ruff](https://docs.astral.sh/ruff/)                          |
| Type checking       | [mypy](https://mypy.readthedocs.io/) (strict, incl. tests)    |
| Tests               | pytest, httpx, polyfactory, testcontainers                    |
| Logging             | [structlog](https://www.structlog.org/) (JSON) + request IDs  |
| Runtime extras      | Docker + compose, CI, rate limiting, Sentry, Temporal, Redis, OTel/Grafana |

## Where to go next

- [Quickstart](quickstart.md) — generate and run a project in a few minutes.
- [Options matrix](options.md) — what each prompt adds to the generated code.
- [Architecture](architecture.md) — the vertical-slice layout and request flow.
- [Recipes](recipes.md) — integration guides shipped inside every project.
- [Upgrading with cruft](upgrading.md) — keep generated projects current.
- [How it compares](https://github.com/mohandoz/fastapi-bedrock#how-it-compares)
  — an honest side-by-side with `full-stack-fastapi-template` and
  `litestar-fullstack`.
