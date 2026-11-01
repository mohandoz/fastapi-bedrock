# Options matrix

Cookiecutter asks for a handful of identity variables and eleven `use_*` feature flags. Every flag adds (or removes) a whole module — dependencies, source files, settings, compose services and tests together — and the template's own CI renders and checks the all-on, all-off and mixed combinations on every change, so any answer set produces a working project.

## Identity variables

| Variable                       | Description                                       | Default               |
| ------------------------------ | ------------------------------------------------- | --------------------- |
| `project_name`                 | Human-readable name                               | `FastAPI DDD Service` |
| `project_slug`                 | Repo/folder name (derived)                        | `fastapi-ddd-service` |
| `package_name`                 | Import package (derived)                          | `fastapi_ddd_service` |
| `project_description`          | One-line description                              | —                     |
| `author_name` / `author_email` | Used in `pyproject.toml` and the API contact info | —                     |
| `version`                      | Initial version                                   | `0.1.0`               |
| `python_version`               | Target Python (`3.13` / `3.14` / `3.12`)          | `3.13`                |
| `first_entity`                 | First domain entity (lowercase snake)             | `item`                |

A pre-generation hook validates the answers (e.g. `first_entity` must be a lowercase snake-case identifier that is not a Python keyword and not `auth`; `python_version` must be one of the supported minors) and fails generation early instead of producing a broken project.

## Feature flags

### `use_auth` — JWT authentication (default: `yes`)

The full account lifecycle as a `domains/auth/` vertical slice:

- **Routes** — register, login (OAuth2 password flow), refresh, logout, `/me` (read/export/delete, GDPR-shaped), password change / forgot / reset, email verification.
- **Tokens** — JWT access + refresh with `iss`/`aud` binding; refresh tokens rotate atomically, and reuse of a rotated token revokes the whole token family (RFC 6819 reuse detection). Families live in Redis when `use_redis=yes`, otherwise in a `refresh_tokens` table. Password changes/resets advance an account version carried by every token, invalidating old sessions and making reset links single-use.
- **Passwords** — Argon2 via `pwdlib`.
- **Email** — password-reset and verification emails (`core/email.py`); full messages are logged only in local development. Other environments emit metadata-only warnings until `EMAILS_ENABLED=true`.
- **Bootstrap** — `FIRST_SUPERUSER_EMAIL`/`FIRST_SUPERUSER_PASSWORD` create or promote a superuser at startup; `OPEN_REGISTRATION=false` makes deployments invite-only.
- **Dependencies added** — `pyjwt`, `pwdlib[argon2]`, `jinja2`.

Disable it for internal services that sit behind a gateway or use mTLS — the `first_entity` routes are then unprotected.

### `use_docker` — containers (default: `yes`)

- Multi-stage `Dockerfile` (uv-based, non-root) and `docker-compose.yml` with PostgreSQL (plus Temporal/Redis/LGTM services when those flags are on), all ports bound to `127.0.0.1`.
- `docker compose watch` support for edit-and-reload inside containers.
- `deploy/k8s/` production-shaped Kubernetes overlays: migration-first rollout, probes, non-root read-only securityContext, file-mounted secrets and optional Redis/Temporal worker Deployments.
- A compose-based `.devcontainer/` (a single-container devcontainer remains when the flag is off).
- `make db-up`, `make docker-up`, `make db-backup` / `db-restore` targets.

Without Docker you point `DATABASE_URL` at your own PostgreSQL; the test suite still needs a Docker daemon for testcontainers.

### `use_github_actions` — CI (default: `yes`)

- `.github/workflows/ci.yml` in the generated project: Ruff, mypy, pytest (with the testcontainers PostgreSQL) and, when `use_docker=yes`, a Docker build smoke test.
- Dependabot config and the PR template remain even when the flag is off — only the workflows are Actions-specific.

### `use_rate_limiting` — slowapi (default: `yes`)

- Global `RATE_LIMIT` (default `100/minute`) per client IP; register, forgot/reset-password, login, refresh, verification and metered LLM routes carry stricter endpoint-specific limits.
- Counters are shared across workers via Redis when `use_redis=yes`, otherwise in-memory per process.
- Adds `slowapi`; documents the `FORWARDED_ALLOW_IPS` / `--proxy-headers` requirements for running behind a proxy.

### `use_sentry` — error tracking (default: `no`)

- `core/sentry.py` initialises `sentry-sdk[fastapi]` when `SENTRY_DSN` is set; traces sampling is configurable (`SENTRY_TRACES_SAMPLE_RATE`).

### `use_temporal` — durable workflows (default: `no`)

- `temporal/` module: client, worker (`make worker`), a demo workflow + activity wired to the first entity, and a router to start it.
- Workflows stay deterministic; side effects (including DB access) live in activities.
- With `use_docker=yes`, compose also starts the Temporal server, Web UI (http://localhost:8080) and a worker container.
- Adds `temporalio`.

### `use_redis` — cache, outbox events, locks (default: `no`)

- **Cache** — typed cache-aside helper (`core/cache.py`, `CacheDep`).
- **Distributed lock** — `core/lock.py` for lease-bounded cross-replica mutual exclusion. Work must finish inside the TTL; irreversible exactly-once effects still need fencing/idempotency.
- **Transactional outbox** — `enqueue_event(session, ...)` writes events in the same DB transaction as your domain change; a relay forwards committed rows to a Redis Stream (CloudEvents 1.0 envelope) and a consumer group processes them at-least-once (`make events-worker`). Poison messages move to a dead-letter stream after `REDIS_MAX_DELIVERY_ATTEMPTS`.
- **Idempotency-Key** — replayable POST responses per the IETF `Idempotency-Key` draft, snapshots stored in Redis.
- Upgrades other flags: shared rate-limit counters, Redis-backed refresh-token families, a Redis testcontainer in the test suite.
- Adds `redis[hiredis]`.

### `use_observability` — OpenTelemetry (default: `no`)

- `core/observability.py` exports traces, metrics and logs over OTLP (`OTEL_ENABLED=true`); FastAPI and SQLAlchemy are auto-instrumented, plus Redis and httpx when those flags are also on.
- With `use_docker=yes`, compose starts `grafana/otel-lgtm` — Collector, Loki, Tempo, Prometheus and Grafana pre-provisioned; logs carry `trace_id`/`span_id` so Loki links straight to Tempo traces.
- Adds the `opentelemetry-*` SDK, OTLP exporter and instrumentation packages.

### `use_http_client` — resilient outbound HTTP (default: `no`)

- `core/http.py` wraps `httpx.AsyncClient` with timeouts, retries (via `stamina`) and a circuit breaker; built once on `app.state`, injected with `HttpClientDep`. Retries fire on network errors and 5xx, never 4xx.
- Adds `stamina` (httpx already ships via `fastapi[standard]`).

### `use_mcp` — MCP server for AI agents (default: `no`)

- Mounts a [FastMCP v3](https://gofastmcp.com/) server at `/mcp` (streamable HTTP) with curated tools over the `first_entity` service layer — `list_*`, `get_*` and `create_*` (`src/<package>/mcp/server.py`). Tools are hand-picked over services, never auto-generated from every route.
- With `use_auth=yes`, requests must carry the same bearer JWT as the REST API (refresh tokens are rejected). Without auth the endpoint is unauthenticated — the pre-gen hook warns against exposing it publicly.
- Adds `fastmcp`.

### `use_llm_example` — Anthropic LLM domain (default: `no`)

- Scaffolds `domains/llm/`: `POST /llm/complete` (structured output via the Anthropic SDK's `messages.parse`) and `POST /llm/stream` (native FastAPI SSE streaming), with settings `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` / `LLM_*`.
- Testing is two-tier: deterministic faked-SDK tests run in CI, plus an opt-in [pydantic-evals](https://ai.pydantic.dev/evals/) lane against the live API (`make evals`). Nothing is required at generation time; the API key is only needed at runtime and for evals.
- Adds `anthropic` (runtime) and `pydantic-evals` (dev).

## Choosing a combination

| You are building…                         | Suggested answers                                                                              |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------- |
| A public API with accounts                | defaults (`use_auth`, `use_docker`, CI, rate limiting)                                         |
| An internal microservice behind a gateway | `use_auth=no`, keep Docker + CI; add `use_observability=yes`                                   |
| An event-driven service                   | `use_redis=yes` (outbox + streams), consider `use_temporal=yes` for long-running orchestration |
| A service calling flaky third parties     | `use_http_client=yes`, `use_observability=yes`                                                 |
| A minimal teaching/example project        | everything `no` — you still get the DDD slice, tests, Alembic, structlog, Ruff and strict mypy |

Flags interact but never conflict: for example `use_redis` upgrades rate limiting and auth storage when those are enabled, and observability instruments whichever of Redis/httpx are present. Any combination renders, lints, type-checks and passes its tests.
