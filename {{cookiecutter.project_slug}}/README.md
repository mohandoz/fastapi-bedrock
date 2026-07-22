# {{ cookiecutter.project_name }}

{{ cookiecutter.project_description }}

Built with FastAPI, SQLModel (SQLAlchemy 2.0 async) and a Domain-Driven Design
layout: each domain is a self-contained vertical slice of models, schemas,
repository, service and router.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Python {{ cookiecutter.python_version }}+ (uv can install it for you)
- Docker — runs PostgreSQL for local development and the test suite

## Quick start

```bash
uv sync                     # create the virtualenv and install dependencies
cp .env.example .env        # then adjust SECRET_KEY / DATABASE_URL
docker compose up -d db     # start PostgreSQL
make run                    # http://127.0.0.1:8000/docs
```

The app runs on PostgreSQL (async, via asyncpg). In the local environment tables
are created automatically on startup; staging and production use Alembic.

## Project layout

```text
src/{{ cookiecutter.package_name }}/
  main.py              # app factory, lifespan, middleware
  core/                # config, database, repository base, logging, security
  api/                 # router aggregation + /health, /ready
  domains/             # one vertical slice per entity
{%- if cookiecutter.use_auth == "yes" %}
    auth/              # users, JWT login/refresh, current-user dependencies
{%- endif %}
    {{ cookiecutter.first_entity }}/               # models · schemas · repository · service · router
{%- if cookiecutter.use_temporal == "yes" %}
  temporal/            # Temporal client, worker, workflows, activities
{%- endif %}
{%- if cookiecutter.use_redis == "yes" %}
  events/              # Redis Streams publisher + consumer worker
{%- endif %}
tests/                 # pytest + testcontainers (PostgreSQL) + httpx + polyfactory
migrations/            # async Alembic migrations
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
make typecheck   Run mypy (strict, src + tests)
make check       Run every check
make audit       Scan dependencies for known CVEs (pip-audit)
make precommit   Run all pre-commit hooks over the tree
make migrate     Apply database migrations
make revision    Create a migration:  make revision m="message"
{%- if cookiecutter.use_temporal == "yes" %}
make worker      Run the Temporal worker
{%- endif %}
{%- if cookiecutter.use_redis == "yes" %}
make events-worker  Run the Redis Streams events consumer
{%- endif %}
{%- if cookiecutter.use_docker == "yes" %}
make db-up       Start only PostgreSQL (pairs with `make run`)
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

Models are created automatically in the local environment. For staging and
production, use Alembic:

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
{%- if cookiecutter.use_temporal == "yes" %}
## Temporal

Durable background workflows via [Temporal](https://temporal.io/). All Temporal
code lives in `src/{{ cookiecutter.package_name }}/temporal/` (client, worker, workflows,
activities, router). Workflows stay deterministic; every side effect (including
DB access) happens inside an activity.

Run the full stack — API, PostgreSQL, Temporal server, Web UI and worker:

```bash
docker compose up --build
```

- Temporal Web UI: http://localhost:8080
- Start the demo workflow: `POST {{ '/api/v1' }}/temporal/{{ cookiecutter.first_entity }}s/{id}/process`

Run the worker alone (against a local `temporal server start-dev`):

```bash
make worker
```
{% endif %}
{%- if cookiecutter.use_redis == "yes" %}
## Redis (cache + events + lock)

An async Redis client (`core/redis.py`) is built once on `app.state` and
injected via `RedisClient`.

- **Caching** — `core/cache.py`, a typed cache-aside helper
  (`cache.get_or_set(...)`), injected with `CacheDep`.
- **Distributed lock** — `core/lock.py` (`distributed_lock(...)`) for
  leader-election / running a scheduled job once across replicas.
- **Durable events (transactional outbox)** — write an event in the *same DB
  transaction* as your domain change with `enqueue_event(session, ...)`; the
  events worker's **relay** forwards committed rows to a **Redis Stream** using
  the **CloudEvents 1.0** envelope, and a consumer group processes them
  (at-least-once, `XACK` + `XAUTOCLAIM`). The CloudEvents `id` is the idempotency
  key. This removes the dual-write race between the database and the broker.

```bash
make events-worker        # runs the outbox relay + the Streams consumer
```

`docker compose up` starts Redis and the events worker.
{% endif %}
{%- if cookiecutter.use_observability == "yes" %}
## Observability (OpenTelemetry + Grafana)

Set `OTEL_ENABLED=true` to export **traces, metrics and logs** over OTLP.
`docker compose up` starts `grafana/otel-lgtm` — one container bundling the
OpenTelemetry Collector, **Loki** (logs), Tempo (traces), Prometheus (metrics)
and **Grafana**, with datasources pre-provisioned.

- Grafana: http://localhost:3000 (admin / admin)
- Logs carry `trace_id` / `span_id`, so Loki links straight to Tempo traces.

FastAPI and SQLAlchemy are auto-instrumented in `core/observability.py`. For
staging/production, point `OTEL_EXPORTER_OTLP_ENDPOINT` at a real Collector —
no app code changes.
{% endif %}
{%- if cookiecutter.use_http_client == "yes" %}
## Resilient HTTP client

`core/http.py` wraps `httpx.AsyncClient` with sane timeouts, **retries** (via
[stamina](https://stamina.hynek.me/)) and a **circuit breaker** for outbound
calls. Built once on `app.state`, injected with `HttpClientDep`:

```python
async def handler(http: HttpClientDep) -> dict[str, str]:
    response = await http.get("https://api.example.com/thing")
    return response.json()
```

Retries fire on network errors and 5xx (not 4xx); the breaker fails fast once a
downstream is consistently failing. With observability enabled, outbound calls
propagate the current trace context automatically.
{% endif %}
## Testing

```bash
make test
```

Tests spin up a throwaway PostgreSQL container with
[testcontainers](https://testcontainers.com/) and drive the API through an async
HTTP client, so **Docker must be running**. No SQLite is used anywhere.

## Maintainability decisions

> Personalise this section for your project — reviewers read it to judge how you
> think. The decisions below are the ones this template already makes.

**Naming.** Each domain is a vertical slice under `domains/<name>/` with the same
five files (`models`, `schemas`, `repository`, `service`, `router`), so any domain
is navigable once you have read one. Schemas are named for intent —
`<Entity>Create` / `<Entity>Update` / `<Entity>Read` — business logic lives in
`*Service`, data access in `*Repository`.

**Type hints.** `mypy --strict` runs over `src` *and* `tests`. Types are strongest
where mistakes cost most: the generic `BaseRepository[Model]`, the service
boundaries, and the request/response schemas Pydantic v2 validates at the edges.
Prefer making illegal states unrepresentable over defensive `if`s.

**Dependencies.** Managed with `uv`; runtime and dev groups are separated and the
resolved `uv.lock` is committed for reproducible installs. Dependabot opens
grouped weekly PRs for Python packages and GitHub Actions.

**Upgrades.** Upgrades arrive as Dependabot PRs and merge only once CI (ruff,
mypy, pytest) is green; `requires-python` sets the floor and the lockfile keeps
every environment identical.

**What the tests protect.** The CRUD contract{% if cookiecutter.use_auth == "yes" %}, the auth flows,{% endif %} and the
health probes — exercised against a real PostgreSQL (via testcontainers) so
behaviour matches production rather than a SQLite stand-in.

**What I'd improve next.** *(your call — e.g. richer pagination metadata,
OpenTelemetry tracing, per-domain integration tests, examples in the OpenAPI
schema, a Redis-backed rate-limit store.)*

---

<p align="center">
  <img src=".github/bedrock-mark.svg" alt="" width="22" valign="middle">
  &nbsp;Scaffolded with <strong>fastapi-bedrock</strong>
</p>
