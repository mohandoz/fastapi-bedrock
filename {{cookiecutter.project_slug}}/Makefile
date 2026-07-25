.DEFAULT_GOAL := help
.PHONY: help setup install run serve test lint format typecheck check audit precommit lock-check migrate revision downgrade new-domain seed clean{% if cookiecutter.use_temporal == "yes" %} worker{% endif %}{% if cookiecutter.use_redis == "yes" %} events-worker{% endif %}{% if cookiecutter.use_docker == "yes" %} db-up db-down docker-up docker-down db-backup db-restore{% endif %}

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## One-command bootstrap: deps, .env, database, migrations, git hooks
	uv sync
	@if [ -f .env ]; then \
		echo ".env already exists - leaving it untouched"; \
	else \
		cp .env.example .env; \
{%- if cookiecutter.use_auth == "yes" %}
		uv run python -c "import pathlib, secrets; p = pathlib.Path('.env'); p.write_text(p.read_text().replace('SECRET_KEY=change-me-to-a-long-random-secret', 'SECRET_KEY=' + secrets.token_urlsafe(48)))"; \
		echo "Created .env with a freshly generated SECRET_KEY"; \
{%- else %}
		echo "Created .env from .env.example"; \
{%- endif %}
	fi
{%- if cookiecutter.use_docker == "yes" %}
	docker compose up -d --wait db
{%- else %}
	@echo "Expecting the PostgreSQL from DATABASE_URL in .env to be running."
{%- endif %}
	uv run alembic upgrade head
	uv run pre-commit install

install: ## Install dependencies and pre-commit hooks
	uv sync
	uv run pre-commit install

run: ## Run the development server with autoreload
	uv run fastapi dev src/{{ cookiecutter.package_name }}/main.py

serve: ## Run the production server
	uv run fastapi run src/{{ cookiecutter.package_name }}/main.py
{%- if cookiecutter.use_temporal == "yes" %}

worker: ## Run the Temporal worker
	uv run python -m {{ cookiecutter.package_name }}.temporal.worker
{%- endif %}
{%- if cookiecutter.use_redis == "yes" %}

events-worker: ## Run the Redis Streams events consumer
	uv run python -m {{ cookiecutter.package_name }}.events.worker
{%- endif %}

test: ## Run the test suite with coverage
	uv run pytest

lint: ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto-format and auto-fix
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## Run mypy
	uv run mypy src tests

check: lint typecheck test ## Run every check (lint, types, tests)

audit: ## Scan locked dependencies for known vulnerabilities
	uv export --no-emit-project --format requirements-txt -o .audit-requirements.txt
	uvx pip-audit -r .audit-requirements.txt; status=$$?; rm -f .audit-requirements.txt; exit $$status

precommit: ## Run all pre-commit hooks against every file
	uv run pre-commit run --all-files

lock-check: ## Fail if uv.lock is out of sync with pyproject.toml
	uv lock --check

migrate: ## Apply all pending database migrations
	uv run alembic upgrade head

revision: ## Autogenerate a migration: make revision m="add users table"
	@test -n "$(m)" || { echo 'Usage: make revision m="message"'; exit 1; }
	uv run alembic revision --autogenerate -m "$(m)"

downgrade: ## Roll back the most recent migration
	uv run alembic downgrade -1

new-domain: ## Scaffold a domain slice: make new-domain name=order
	@test -n "$(name)" || { echo 'Usage: make new-domain name=<snake_case_name>'; exit 1; }
	uv run python scripts/new_domain.py "$(name)"

seed: ## Seed the local database with demo data (idempotent, local only)
	uv run python scripts/seed.py

clean: ## Remove caches and build artefacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage coverage.xml dist build .audit-requirements.txt
	find . -type d -name __pycache__ -exec rm -rf {} +
{%- if cookiecutter.use_docker == "yes" %}

db-up: ## Start only the PostgreSQL container in the background
	docker compose up -d db

db-down: ## Stop the PostgreSQL container (data is preserved)
	docker compose stop db

db-backup: ## Dump the database to backups/<timestamp>.dump (pg_dump custom format)
	@mkdir -p backups
	docker compose exec -T db pg_dump -U postgres -Fc {{ cookiecutter.package_name }} > backups/$$(date +%Y%m%d-%H%M%S).dump
	@ls -t backups | head -1 | sed 's|^|Wrote backups/|'

db-restore: ## Restore a dump: make db-restore f=backups/<file>.dump
	@test -n "$(f)" || { echo 'Usage: make db-restore f=backups/<file>.dump'; exit 1; }
	docker compose exec -T db pg_restore -U postgres --clean --if-exists -d {{ cookiecutter.package_name }} < $(f)

docker-up: ## Build and start the full stack (api + database)
	docker compose up --build

docker-down: ## Stop the stack and remove volumes
	docker compose down -v
{%- endif %}
