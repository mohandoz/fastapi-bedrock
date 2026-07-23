# {{ cookiecutter.project_name }}

{{ cookiecutter.project_description }}

Built with FastAPI, SQLModel (SQLAlchemy 2.0 async) and a Domain-Driven Design
layout: each domain is a self-contained vertical slice of models, schemas,
repository, service and router.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Python {{ cookiecutter.python_version }}+ (uv can install it for you)
{%- if cookiecutter.use_docker == "yes" %}
- Docker — runs PostgreSQL for local development and the test suite
{%- else %}
- PostgreSQL — a running instance for local development (see `DATABASE_URL`)
- Docker — runs the test suite's throwaway PostgreSQL (testcontainers)
{%- endif %}

## Quick start
{% if cookiecutter.use_docker == "yes" %}
```bash
uv sync                     # create the virtualenv and install dependencies
cp .env.example .env        # then adjust {% if cookiecutter.use_auth == "yes" %}SECRET_KEY / {% endif %}DATABASE_URL
docker compose up -d db     # start PostgreSQL
make run                    # http://127.0.0.1:8000/docs
```
{%- else %}
```bash
uv sync                     # create the virtualenv and install dependencies
cp .env.example .env        # point DATABASE_URL at your PostgreSQL{% if cookiecutter.use_auth == "yes" %}, set SECRET_KEY{% endif %}
make run                    # http://127.0.0.1:8000/docs
```
{%- endif %}

The app runs on PostgreSQL (async, via asyncpg). In the local environment tables
are created automatically on startup; staging and production use Alembic.

## Project layout

```text
src/{{ cookiecutter.package_name }}/
  main.py              # app factory, lifespan, middleware
  core/                # config, database, repository base, logging{% if cookiecutter.use_auth == "yes" %}, security{% endif %}
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
{%- if cookiecutter.use_rate_limiting == "yes" %}
## Rate limiting

Every route is limited to `RATE_LIMIT` (default `100/minute`) per client IP.
{%- if cookiecutter.use_auth == "yes" %}
`POST {{ '{prefix}' }}/auth/register` is stricter (`5/minute`): registration is
unauthenticated and abusable.
{%- endif %}
{%- if cookiecutter.use_redis == "yes" %}
Counters live in Redis, so limits are shared across workers and replicas and
survive restarts; a Redis outage degrades to per-process in-memory counting.
{%- else %}
Counters are in-memory and per-process: with multiple workers the effective
limit multiplies by the worker count, and counters reset on every restart.
{%- endif %}

**Behind a reverse proxy or load balancer** the peer address is the proxy's, so
all clients collapse into one shared bucket unless forwarded headers are
{%- if cookiecutter.use_docker == "yes" %}
trusted. The container CMD (`fastapi run`) already passes uvicorn
`--proxy-headers`; also set `FORWARDED_ALLOW_IPS=<proxy address>` on the
container so the forwarded header is honored — and only from that proxy.
{%- else %}
trusted. Run uvicorn with `--proxy-headers` and set
`FORWARDED_ALLOW_IPS=<proxy address>` so the forwarded header is honored — and
only from that proxy.
{%- endif %}
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
All published ports bind to `127.0.0.1` only; setting `POSTGRES_PASSWORD` in
`.env` overrides the local PostgreSQL password across the whole compose stack.
{% endif %}
{%- if cookiecutter.use_temporal == "yes" %}
## Temporal

Durable background workflows via [Temporal](https://temporal.io/). All Temporal
code lives in `src/{{ cookiecutter.package_name }}/temporal/` (client, worker, workflows,
activities, router). Workflows stay deterministic; every side effect (including
DB access) happens inside an activity.
{% if cookiecutter.use_docker == "yes" %}
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
{%- else %}
Run a local development server ([Temporal CLI](https://docs.temporal.io/cli)),
the worker and the API:

```bash
temporal server start-dev   # Temporal server + Web UI on http://localhost:8233
make worker                 # in a second terminal
make run                    # in a third terminal
```

Start the demo workflow: `POST {{ '/api/v1' }}/temporal/{{ cookiecutter.first_entity }}s/{id}/process`
{%- endif %}
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
  The consumer periodically reclaims stale pending entries (`XAUTOCLAIM`) and
  trims fully processed ones (`XTRIM MINID`); `REDIS_STREAM_MAXLEN` (default
  1,000,000) is only an approximate hard cap on unprocessed backlog — monitor
  `XLEN`/`XPENDING`. Requires Redis >= 6.2.

```bash
make events-worker        # runs the outbox relay + the Streams consumer
```
{% if cookiecutter.use_docker == "yes" %}
`docker compose up` starts Redis and the events worker.
{%- else %}
Requires a running Redis — install it locally (`brew install redis` /
`apt install redis-server`) and point `REDIS_URL` at it.
{%- endif %}
{% endif %}
{%- if cookiecutter.use_observability == "yes" %}
## Observability (OpenTelemetry + Grafana)
{% if cookiecutter.use_docker == "yes" %}
Set `OTEL_ENABLED=true` to export **traces, metrics and logs** over OTLP.
`docker compose up` starts `grafana/otel-lgtm` — one container bundling the
OpenTelemetry Collector, **Loki** (logs), Tempo (traces), Prometheus (metrics)
and **Grafana**, with datasources pre-provisioned.
{%- else %}
Set `OTEL_ENABLED=true` to export **traces, metrics and logs** over OTLP, and
point `OTEL_EXPORTER_OTLP_ENDPOINT` at an OpenTelemetry Collector. For local
work, `docker run --rm -p 3000:3000 -p 4318:4318 grafana/otel-lgtm` bundles the
Collector, **Loki** (logs), Tempo (traces), Prometheus (metrics) and
**Grafana**, with datasources pre-provisioned.
{%- endif %}

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

## Production checklist

Unsafe configuration fails at boot (`core/config.py`) instead of silently
degrading:
{% if cookiecutter.use_auth == "yes" %}
- `SECRET_KEY` must be overridden and at least 32 characters everywhere outside
  `local` (staging **and** production); the shipped default is rejected.
{%- endif %}
- In production, `DEBUG` must be `false` and `ALLOWED_HOSTS` must list explicit
  hostnames (`*` is rejected).
- `/docs`, `/redoc` and the OpenAPI schema are disabled in production unless
  `DOCS_ENABLED=true` is set explicitly.
{%- if cookiecutter.use_auth == "yes" %}
- `OPEN_REGISTRATION` (default `true`) controls public signup; set it to `false`
  for invite-only deployments — `POST {{ '{prefix}' }}/auth/register` then
  returns 403.
{%- endif %}
{%- if cookiecutter.use_rate_limiting == "yes" %}
- Behind a proxy, set `FORWARDED_ALLOW_IPS` so rate limits key on real client
  IPs (see [Rate limiting](#rate-limiting)).
{%- endif %}

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
resolved `uv.lock` is committed for reproducible installs.
Dependabot opens grouped weekly PRs for Python packages and GitHub Actions.
{% if cookiecutter.use_github_actions == "yes" %}
**Upgrades.** Upgrades arrive as Dependabot PRs and merge only once CI (ruff,
mypy, pytest) is green; `requires-python` sets the floor and the lockfile keeps
every environment identical.
{%- else %}
**Upgrades.** Refresh the lockfile deliberately with `uv lock --upgrade` and
merge only once `make check` (ruff, mypy, pytest) passes; `requires-python` sets
the floor and the lockfile keeps every environment identical.
{%- endif %}

**What the tests protect.** The CRUD contract{% if cookiecutter.use_auth == "yes" %}, the auth flows,{% endif %} and the
health probes — exercised against a real PostgreSQL (via testcontainers) so
behaviour matches production rather than a SQLite stand-in.

**What I'd improve next.** *(your call — e.g. richer pagination metadata,
{%- if cookiecutter.use_observability == "no" %} OpenTelemetry tracing,{% endif %}
per-domain integration tests, examples in the OpenAPI schema
{%- if cookiecutter.use_rate_limiting == "no" or cookiecutter.use_redis == "no" %},
a Redis-backed rate-limit store{% endif %}.)*

---

<p align="center">
  <img src=".github/bedrock-mark.svg" alt="" width="22" valign="middle">
  &nbsp;Scaffolded with <strong>fastapi-bedrock</strong>
</p>
