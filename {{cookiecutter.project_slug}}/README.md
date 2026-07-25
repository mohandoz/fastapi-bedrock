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
make setup                  # deps, .env{% if cookiecutter.use_auth == "yes" %} + generated SECRET_KEY{% endif %}, PostgreSQL, migrations, git hooks
make run                    # http://127.0.0.1:8000/docs
```
{%- else %}
```bash
# Requires a running PostgreSQL matching DATABASE_URL (default: postgres:postgres@localhost:5432)
make setup                  # deps, .env{% if cookiecutter.use_auth == "yes" %} + generated SECRET_KEY{% endif %}, migrations, git hooks
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
make setup       One-command bootstrap: deps, .env, database, migrations, git hooks
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
make new-domain  Scaffold a domain slice:  make new-domain name=order
make seed        Seed the local database with demo data
make loadtest    Run the k6 load test:  BASE_URL=... make loadtest
make openapi     Export the OpenAPI schema to openapi.json
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

## CLI

The package installs a `{{ cookiecutter.project_slug }}` console script for
operational tasks:

```bash
uv run {{ cookiecutter.project_slug }} --help
```

{% if cookiecutter.use_auth == "yes" -%}
- `createsuperuser` — create a verified superuser, or promote an existing user
{% endif -%}
- `migrate` — Alembic passthrough (defaults to `upgrade head`)
- `seed` — seed the local database with demo data
- `openapi-export` — write `openapi.json` without starting the server

## Error format

All error responses are [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html)
`application/problem+json` documents:

```json
{
  "type": "urn:problem-type:not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "Item 42 not found",
  "instance": "/api/v1/items/42"
}
```

`type` is a stable machine-readable identifier (`urn:problem-type:*` for domain
errors — not-found, conflict, unauthorized, forbidden,
validation-error,{% if cookiecutter.use_rate_limiting == "yes" %} rate-limited,{% endif %} internal-error — and `about:blank` for plain
HTTP errors). Validation failures (422) add an `errors` array listing the
failing fields. Every response carries an `X-Request-ID` header (echoed from
the request or generated) — include it when reporting issues. Access logging is
one structured `request_completed` event per request (uvicorn's plain access
log is disabled).
{% if cookiecutter.use_auth == "yes" %}
## Authentication

JWT bearer authentication using the OAuth2 password flow:

- `POST {{ '{prefix}' }}/auth/register` — create an account
- `POST {{ '{prefix}' }}/auth/login` — exchange credentials for access + refresh tokens
- `POST {{ '{prefix}' }}/auth/refresh` — rotate the refresh token, mint a new pair
- `POST {{ '{prefix}' }}/auth/logout` — revoke the refresh-token family
- `GET  {{ '{prefix}' }}/auth/me` — the current user
- `GET  {{ '{prefix}' }}/auth/me/export` — the account's stored data as JSON (GDPR portability)
- `DELETE {{ '{prefix}' }}/auth/me` — erase the account (GDPR erasure, hard delete)
- `POST {{ '{prefix}' }}/auth/password` — change the password (requires the current one)
- `POST {{ '{prefix}' }}/auth/forgot-password` — email a password-reset link (always 202)
- `POST {{ '{prefix}' }}/auth/reset-password` — set a new password with the emailed token
- `POST {{ '{prefix}' }}/auth/verify-email` — confirm an email address

where `{{ '{prefix}' }}` is `{{ '/api/v1' }}` by default. The `{{ cookiecutter.first_entity }}`
routes are protected and require a valid access token.

Outbound email is logged instead of sent until `EMAILS_ENABLED=true` with
`SMTP_*` configured (`core/email.py`), so local development needs no SMTP
server. Reset and verification links point at `FRONTEND_URL` and expire after
`EMAIL_TOKEN_EXPIRE_MINUTES`; set `REQUIRE_EMAIL_VERIFICATION=true` to block
login until the address is verified.

Refresh tokens rotate: each refresh invalidates the presented token, and
reusing an already-rotated token is treated as theft — the whole token family
is revoked (RFC 6819 reuse detection).
{%- if cookiecutter.use_redis == "yes" %}
Families are tracked in Redis and expire with their newest token.
{%- else %}
Families are tracked in the `refresh_tokens` table; expired rows are purged as
users log in.
{%- endif %}
Tokens carry `aud`/`iss` claims (`JWT_AUDIENCE`/`JWT_ISSUER`), so another
service sharing the same `SECRET_KEY` still rejects them.

Set `FIRST_SUPERUSER_EMAIL` and `FIRST_SUPERUSER_PASSWORD` to create (or
promote) a superuser at startup; guard admin routes with the `CurrentSuperuser`
dependency from `domains/auth/dependencies.py`.
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
trusted. The container CMD already passes uvicorn `--proxy-headers`; also set
`FORWARDED_ALLOW_IPS=<proxy address>` on the container so the forwarded header
is honored — and only from that proxy.
{%- else %}
trusted. Run uvicorn with `--proxy-headers` and set
`FORWARDED_ALLOW_IPS=<proxy address>` so the forwarded header is honored — and
only from that proxy.
{%- endif %}
{% endif %}
## Database migrations

Alembic owns the schema in staging and production. Locally, tables are
auto-created at startup for convenience (`DB_AUTO_CREATE`, on by default only
when `ENVIRONMENT=local`). Generate revisions against a database that contains
only what migrations created — an auto-created schema yields an empty revision
(see `migrations/README`):

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

`docker compose watch` (or `up --watch`) gives an edit-and-reload loop inside
Docker: changes to `src/` and `migrations/` sync into the api container and
restart uvicorn; `pyproject.toml` / `uv.lock` changes rebuild the image.

Back up the local database with `make db-backup` (writes
`backups/<timestamp>.dump`) and restore with
`make db-restore f=backups/<file>.dump` — `make docker-down` removes the
data volume, so back up first.

## Deployment

`deploy/k8s/` ships minimal production-shaped Kubernetes manifests: probes
wired to `/api/v1/health` (liveness) and `/api/v1/ready` (readiness),
graceful-shutdown timing matched to the image, a non-root read-only
securityContext, file-mounted secrets and a replicated-safe migration Job.
See [deploy/README.md](deploy/README.md).
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

### Idempotency-Key

`POST /api/v1/{{ cookiecutter.first_entity }}s` honours the `Idempotency-Key`
header (IETF `draft-ietf-httpapi-idempotency-key`): send a unique key (a UUID)
and a retry with the same key and body replays the original response
(`Idempotent-Replayed: true`) instead of creating a duplicate. A retry while
the first attempt is still in flight is answered 409, and reusing a key with a
different body is answered 422. Snapshots live in Redis for `IDEMPOTENCY_TTL`
seconds. Opt further POST routes in with the `@idempotent` marker from
`core/idempotency.py`, on a router built with `route_class=IdempotentAPIRoute`.
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
## Scaffolding a new domain

```bash
make new-domain name=order
```

Creates `src/{{ cookiecutter.package_name }}/domains/order/` (models, schemas,
repository, service, router) plus `tests/test_order.py`, mirroring the
`{{ cookiecutter.first_entity }}` slice, and prints the three registration
lines to add (API router, `_import_models`, `migrations/env.py`). Fill the
local database with demo data via `make seed`.

## Recipes

`docs/recipes/` holds integration guides written against this codebase:

- [Background work: which tool?](docs/recipes/background-jobs.md) —
  `BackgroundTasks` vs the transactional outbox vs Temporal, with a decision
  table and one example each. Read it before adding any async work.
{%- if cookiecutter.use_auth == "yes" %}
- [Social login (OAuth / OIDC) with Authlib](docs/recipes/oauth-social-login.md)
{%- endif %}
- [Admin back-office with SQLAdmin](docs/recipes/admin-sqladmin.md)
- [Feature flags with OpenFeature](docs/recipes/feature-flags-openfeature.md)

`.python-version` pins the interpreter (uv reads it directly); mise users can
copy `docs/mise.toml.example` to `mise.toml` for the same pins.

## Editor / dev container

`.devcontainer/` runs the project in VS Code Dev Containers or GitHub
Codespaces{% if cookiecutter.use_docker == "yes" %} (compose-based: it starts and joins the `db`{% if cookiecutter.use_redis == "yes" %} and `redis`{% endif %} services){% endif %};
the shipped `.vscode/` settings enable Ruff format-on-save and pytest
discovery. See `CONTRIBUTING.md` for commit conventions and the cruft
update workflow.

## Testing

```bash
make test
```

Tests spin up a throwaway PostgreSQL container with
[testcontainers](https://testcontainers.com/) and drive the API through an async
HTTP client, so **Docker must be running**. No SQLite is used anywhere.

## Load testing

`loadtest/` contains a k6 script with smoke and ramp scenarios over the health
probe and {{ cookiecutter.first_entity }} CRUD. With the API running:
`make loadtest` (point elsewhere with `BASE_URL=...`). See
`loadtest/README.md` for thresholds and options.

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
- `EMAILS_ENABLED=true` requires `SMTP_HOST` (rejected at boot otherwise).
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

**Tooling.** `make` over `just`: preinstalled everywhere (dev machines, CI,
containers) and these targets stay inside the portable subset — a task runner
nobody has to install beats a nicer one somebody must. `uvicorn` over
`granian`: its operational surface (`--proxy-headers`,
`--timeout-graceful-shutdown`, `FORWARDED_ALLOW_IPS`) is battle-tested{% if cookiecutter.use_docker == "yes" %} and is
what the Dockerfile, compose file and k8s manifests are tuned around{% endif %}; revisit
only if profiling shows the ASGI server itself is the bottleneck.
`mypy --strict` over `ty`: mypy is the reference checker and the pydantic
plugin depends on it; `ty` is tracked as a likely drop-in speedup once stable.

**Pagination.** Offset/limit with a deterministic `ORDER BY` is the default —
simple, stateless, and fine at the row counts most listing endpoints see. The
upgrade path is keyset (cursor) pagination per repository once a table grows
past what `OFFSET` scans tolerate; `BaseRepository.list` documents the
override point.

**Dependencies.** Managed with `uv`; runtime and dev groups are separated and the
resolved `uv.lock` is committed for reproducible installs.
Dependabot opens grouped weekly PRs for Python packages{% if cookiecutter.use_github_actions == "yes" %} and GitHub Actions{% endif %}{% if cookiecutter.use_docker == "yes" %}, plus Docker and Compose base images{% endif %}.
Pre-commit hook revs are pinned in `.pre-commit-config.yaml`; refresh them with
`pre-commit autoupdate`, or enable the repo on [pre-commit.ci](https://pre-commit.ci)
— the shipped config already carries a `ci:` block for it.
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
