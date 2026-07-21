.DEFAULT_GOAL := help
.PHONY: help install run serve test lint format typecheck check migrate revision downgrade clean{% if cookiecutter.use_docker == "yes" %} docker-up docker-down{% endif %}

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies and pre-commit hooks
	uv sync
	uv run pre-commit install

run: ## Run the development server with autoreload
	uv run fastapi dev src/{{ cookiecutter.package_name }}/main.py

serve: ## Run the production server
	uv run fastapi run src/{{ cookiecutter.package_name }}/main.py

test: ## Run the test suite with coverage
	uv run pytest

lint: ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto-format and auto-fix
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## Run mypy
	uv run mypy src

check: lint typecheck test ## Run every check (lint, types, tests)

migrate: ## Apply all pending database migrations
	uv run alembic upgrade head

revision: ## Autogenerate a migration: make revision m="add users table"
	uv run alembic revision --autogenerate -m "$(m)"

downgrade: ## Roll back the most recent migration
	uv run alembic downgrade -1

clean: ## Remove caches and build artefacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage coverage.xml dist build
	find . -type d -name __pycache__ -exec rm -rf {} +
{%- if cookiecutter.use_docker == "yes" %}

docker-up: ## Build and start the full stack (api + database)
	docker compose up --build

docker-down: ## Stop the stack and remove volumes
	docker compose down -v
{%- endif %}
