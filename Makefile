.DEFAULT_GOAL := help
.PHONY: help install fmt lint types contracts test check clean

help: ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Sync dependencies and install the project
	uv sync

fmt: ## Format
	uv run ruff format src tests migrations
	uv run ruff check --fix src tests migrations

lint: ## Lint (no fixes)
	uv run ruff format --check src tests migrations
	uv run ruff check src tests migrations

types: ## Type-check
	uv run mypy

contracts: ## Verify the architectural import contracts
	uv run lint-imports

db-up: ## Provision local Postgres roles and databases (idempotent)
	PGHOST=$${PGHOST:-localhost} PGUSER=$${PGUSER:-$$(whoami)} ./scripts/bootstrap_local_db.sh

migrate: ## Apply migrations to the dev database
	uv run alembic upgrade head

test: ## Run tests (needs db-up + migrate against softbox_test first)
	uv run pytest

check: lint types contracts test ## Everything CI runs

clean: ## Remove caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
