<p align="center">
  <img src="assets/logo.svg" alt="fastapi-bedrock" width="360">
</p>

<p align="center">
  <em>The solid, layered foundation you build your FastAPI service on.</em>
</p>

<p align="center">
  <a href="https://github.com/mohandoz/fastapi-bedrock/actions/workflows/test-template.yml"><img src="https://github.com/mohandoz/fastapi-bedrock/actions/workflows/test-template.yml/badge.svg" alt="Test template"></a>
  <a href="https://scorecard.dev/viewer/?uri=github.com/mohandoz/fastapi-bedrock"><img src="https://api.scorecard.dev/projects/github.com/mohandoz/fastapi-bedrock/badge" alt="OpenSSF Scorecard"></a>
  <a href="https://github.com/mohandoz/fastapi-bedrock/actions/workflows/codeql.yml"><img src="https://github.com/mohandoz/fastapi-bedrock/actions/workflows/codeql.yml/badge.svg" alt="CodeQL"></a>
  <a href="https://mohandoz.github.io/fastapi-bedrock/"><img src="https://img.shields.io/badge/docs-mohandoz.github.io-009485" alt="Documentation"></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/types-mypy%20strict-blue" alt="mypy strict">
  <img src="https://img.shields.io/badge/lint-ruff-D7FF64" alt="Ruff">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license">
</p>

> [!NOTE]
> **Not related to Amazon Bedrock.** *Bedrock* here means what it says on the
> tin — the solid layer of rock you build on. This is a Cookiecutter template
> for FastAPI backend services; for AWS's managed LLM platform, see
> [Amazon Bedrock](https://aws.amazon.com/bedrock/).

A modern [Cookiecutter](https://cookiecutter.readthedocs.io/) template for
production-ready **FastAPI** services organised with a **Domain-Driven Design**
(vertical-slice) layout — the solid foundation you build your service on.
Full documentation lives at
**[mohandoz.github.io/fastapi-bedrock](https://mohandoz.github.io/fastapi-bedrock/)**.

Every generated project ships fully wired: async database access, a clean
repository/service layering, JWT authentication, tests, linting, typing,
Docker and CI — nothing to bolt on afterwards.

## Stack

| Concern             | Choice                                                             |
| ------------------- | ----------------------------------------------------------------- |
| Language            | Python 3.12 / 3.13 / 3.14 (defaults to 3.13)                      |
| Packaging / env     | [uv](https://docs.astral.sh/uv/) (PEP 621 + PEP 735)             |
| Web framework       | [FastAPI](https://fastapi.tiangolo.com/) (`fastapi[standard]`)    |
| Data / ORM          | [SQLModel](https://sqlmodel.tiangolo.com/) on SQLAlchemy 2.0 async — PostgreSQL / asyncpg |
| Migrations          | [Alembic](https://alembic.sqlalchemy.org/) (async)                |
| Validation / config | Pydantic v2 + `pydantic-settings`                                 |
| Auth                | OAuth2 password flow, JWT access + refresh, Argon2 (`pwdlib`)     |
| Lint + format       | [Ruff](https://docs.astral.sh/ruff/) (replaces black + isort)     |
| Type checking       | [mypy](https://mypy.readthedocs.io/) (strict, incl. tests)        |
| Tests               | pytest, httpx, polyfactory, testcontainers (real PostgreSQL)      |
| Logging             | [structlog](https://www.structlog.org/) (JSON) + request IDs      |
| Runtime extras      | Docker + compose, CI, rate limiting, Sentry, Temporal, Redis, OTel/Grafana |
| Dev experience      | devcontainer + VS Code presets, `make new-domain` scaffolder, `make seed`, keep-a-changelog + conventional commits |

## How it compares

Both alternatives below are excellent — this table exists to route you to the
right one, not to win. The short version: **fastapi-bedrock is backend-only
and composable**; the others ship a frontend and a fixed feature set.

| | **fastapi-bedrock** | [full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) | [litestar-fullstack](https://github.com/litestar-org/litestar-fullstack) |
| --- | --- | --- | --- |
| What it is | Backend-only cookiecutter template | Official FastAPI full-stack template | Litestar reference application |
| Framework | FastAPI | FastAPI | Litestar |
| Frontend | None — API-first by design | React + TS, Vite, Tailwind, shadcn/ui, generated API client, dark mode | React + Vite |
| ORM | SQLModel (SQLAlchemy 2.0, fully async) | SQLModel | SQLAlchemy 2.0 (Advanced Alchemy) |
| Architecture | DDD vertical slices; repository → service → router | App-package layout | Service/repository patterns |
| Feature selection | 11 opt-in/out flags, every combination CI-baked | Fixed feature set | Fixed feature set |
| Generation & updates | cookiecutter + `cruft update` diffs | Clone or Copier | Clone/fork |
| Auth | JWT access + refresh **rotation with reuse detection**, Argon2, email verification, GDPR export/erase | JWT + password recovery | JWT, MFA, OAuth, roles/teams — the richest auth of the three |
| Background work | Temporal durable workflows + transactional outbox → Redis Streams (CloudEvents) | — | SAQ task queue |
| Observability | OpenTelemetry traces/metrics/logs + Grafana LGTM stack (optional) | — | structlog |
| Rate limiting | slowapi, Redis-shared counters (optional) | — | — |
| Error format | RFC 9457 `problem+json` throughout | FastAPI defaults | Litestar defaults |
| Tests | pytest + testcontainers (**real PostgreSQL**) | pytest + Playwright E2E | pytest |
| Typing | `mypy --strict` over `src` *and* `tests` | mypy | mypy |
| Deployment | Docker + compose, k8s manifests | Docker compose + Traefik guides | Docker multi-stage, distroless variant |
| Community | Young, single maintainer | Official FastAPI org — by far the largest community | Litestar org |

**Choose full-stack-fastapi-template** if you want a working UI on day one,
the official FastAPI path, and the reassurance of a huge community.
**Choose litestar-fullstack** if you prefer Litestar's batteries (its auth
surface — MFA, OAuth, teams — is genuinely richer) and don't need FastAPI.
**Choose fastapi-bedrock** for backend services and microservices where the
frontend lives elsewhere, and you want durable workflows, event-driven
patterns and observability composed per-project — with `cruft` keeping
generated projects updatable.

## Architecture

The generated project follows a **repository → service → router** flow with
each domain as a self-contained vertical slice:

```mermaid
flowchart LR
    client((Client)) --> mw["middleware<br>request-id, security headers,<br>CORS, body-size limit"]
    mw --> api["api router<br>/api/v1"]
    api --> health["/health, /ready"]
    api --> auth["auth router (JWT)"]
    api --> dom["&lt;entity&gt; router"]
    auth --> asvc["auth service"]
    dom --> svc["&lt;entity&gt; service"]
    asvc --> urepo["user repository"]
    svc --> repo["&lt;entity&gt; repository"]
    urepo --> db[(PostgreSQL)]
    repo --> db
    svc -.->|outbox event| stream[(Redis Stream)]
    svc -.->|start workflow| temporal["Temporal"]
```

*Dashed arrows are optional slices (`use_redis`, `use_temporal`); the auth
slice ships with `use_auth=yes`.*

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
# recommended: cruft, so generated projects can pull template updates later
uvx cruft create gh:mohandoz/fastapi-bedrock

# plain cookiecutter works too (no update tracking)
uvx cookiecutter gh:mohandoz/fastapi-bedrock

# deterministic, prompt-free scaffold (CI and coding agents; unset options keep defaults)
uvx cookiecutter gh:mohandoz/fastapi-bedrock --no-input \
  project_name="Acme API" first_entity=order use_auth=yes use_docker=yes use_mcp=yes
```

[cruft](https://cruft.github.io/cruft/) records the template revision in
`.cruft.json`, so a generated project can later run `uvx cruft update` to pull
in template improvements as a reviewable diff (the generated `CONTRIBUTING.md`
documents the workflow). You will be prompted for the variables below. When
generation finishes the hook initialises a fresh git repository and runs
`uv sync` (set the env var `SKIP_UV_SYNC=1` to opt out).

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
| `python_version`      | Target Python (`3.13` / `3.14` / `3.12`)  | `3.13`                |
| `first_entity`        | First domain entity (lowercase snake)     | `item`                |
| `use_auth`            | Include JWT authentication                | `yes`                 |
| `use_docker`          | Include Dockerfile + docker-compose       | `yes`                 |
| `use_github_actions`  | Include CI workflow                       | `yes`                 |
| `use_rate_limiting`   | Include slowapi rate limiting             | `yes`                 |
| `use_sentry`          | Include Sentry error tracking             | `no`                  |
| `use_temporal`        | Include Temporal.io durable workflows     | `no`                  |
| `use_redis`           | Redis cache + outbox/Streams events + lock | `no`                 |
| `use_observability`   | Include OpenTelemetry + Grafana/Loki/Tempo| `no`                  |
| `use_http_client`     | Resilient outbound HTTP client            | `no`                  |
| `use_mcp`             | MCP server (FastMCP v3) for AI agents at `/mcp` | `no`            |
| `use_llm_example`     | Anthropic LLM domain: structured output + SSE | `no`              |

## What you get after generation

```bash
cd <project_slug>
make setup                  # deps, .env (+ generated SECRET_KEY), database, migrations, git hooks
make run                    # uv run fastapi dev  ->  http://127.0.0.1:8000/docs
make test                   # pytest against a testcontainers PostgreSQL (needs Docker)
make lint                   # ruff check + format check
make typecheck              # mypy --strict (src + tests)
make new-domain name=order  # scaffold a full vertical slice + tests
make seed                   # fill the local database with demo data
```

The app runs on PostgreSQL (async, via asyncpg); `docker-compose.yml` provides a
local database and — when `use_temporal` is enabled — a Temporal server + worker.
Tables are auto-created in the local environment; staging and production use Alembic.

Each project also ships a `.devcontainer/` (VS Code Dev Containers / GitHub
Codespaces ready, compose-based when `use_docker=yes`), `.vscode/` presets
(Ruff format-on-save, pytest discovery), a keep-a-changelog `CHANGELOG.md` and
a `CONTRIBUTING.md` covering conventional commits and the `cruft update`
workflow.

## Documentation & community

The **[docs site](https://mohandoz.github.io/fastapi-bedrock/)** covers what a
README can't: a [quickstart](https://mohandoz.github.io/fastapi-bedrock/quickstart/),
the full [options matrix](https://mohandoz.github.io/fastapi-bedrock/options/)
for the eleven `use_*` flags, the
[architecture tour](https://mohandoz.github.io/fastapi-bedrock/architecture/),
the shipped [recipes](https://mohandoz.github.io/fastapi-bedrock/recipes/) and
the [cruft upgrade guide](https://mohandoz.github.io/fastapi-bedrock/upgrading/).
It also serves [`/llms.txt`](https://mohandoz.github.io/fastapi-bedrock/llms.txt)
for AI assistants.

- **Questions about your generated project** →
  [Discussions](https://github.com/mohandoz/fastapi-bedrock/discussions)
- **Bugs in the template itself** →
  [issue forms](https://github.com/mohandoz/fastapi-bedrock/issues/new/choose)
- **Contributing** → [CONTRIBUTING.md](CONTRIBUTING.md) (template-specific
  workflows: rendering locally, the CI bake matrix, Jinja gotchas), governed
  by the [Code of Conduct](CODE_OF_CONDUCT.md)

## License

MIT — see [LICENSE](LICENSE).
