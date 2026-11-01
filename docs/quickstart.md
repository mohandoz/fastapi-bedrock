# Quickstart

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — used both to run the generator (`uvx`)
  and to manage the generated project.
- Docker — the test suite starts a throwaway PostgreSQL via
  [testcontainers](https://testcontainers.com/), and local development uses a
  compose-managed database when `use_docker=yes`.

## Generate a project

```bash
# recommended: cruft, so the project can pull template updates later
uvx cruft create https://github.com/mohandoz/fastapi-bedrock

# plain cookiecutter works too (no update tracking)
uvx cookiecutter gh:mohandoz/fastapi-bedrock
```

You will be prompted for the project name, author details, target Python
version, the name of your first domain entity, and the nine `use_*` feature
flags — the [options matrix](options.md) explains exactly what each one adds.

When generation finishes, a post-generation hook prunes the modules you
disabled, initialises a git repository, runs `uv sync` and makes an initial
commit. Set the environment variable `SKIP_UV_SYNC=1` to skip dependency
installation (you must then run `uv sync` yourself before the first push, so
`uv.lock` gets committed).

### Non-interactive generation

Every variable can be supplied on the command line, which is handy for CI and
for trying variants quickly:

```bash
uvx cookiecutter gh:mohandoz/fastapi-bedrock --no-input \
  project_name="Order Service" \
  use_temporal=yes use_redis=yes use_observability=yes
```

## Run it

```bash
cd <project_slug>
make setup                  # deps, .env (+ generated SECRET_KEY), database, migrations, git hooks
make run                    # uv run fastapi dev  ->  http://127.0.0.1:8000/docs
```

The interactive API docs live at `/docs`, health probes at
`/api/v1/health` and `/api/v1/ready`.

## The everyday loop

```bash
make test                   # pytest against a testcontainers PostgreSQL
make lint                   # ruff check + format check
make typecheck              # mypy --strict (src + tests)
make check                  # all of the above
make new-domain name=order  # scaffold a full vertical slice + tests
make seed                   # fill the local database with demo data
```

With `use_docker=yes`, `docker compose up --build` starts the full stack, and
`docker compose watch` gives an edit-and-reload loop inside Docker.

## Next steps

- Read the [architecture](architecture.md) page to understand the layout
  before adding your first real domain.
- Skim the [recipes](recipes.md) — social login, admin UI, background-job
  guidance, anti-bot verification and passkeys are all written against the
  generated codebase.
- If you generated with cruft, note the `.cruft.json` at the project root:
  it is what makes [template updates](upgrading.md) possible later.
