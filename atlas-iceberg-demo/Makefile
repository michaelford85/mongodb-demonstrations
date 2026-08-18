# Atlas → Iceberg reference-pattern demo.
# All targets are copy/paste runnable from this directory.

SHELL := /bin/bash
PY    := python3
COMPOSE := docker compose

.DEFAULT_GOAL := help
.PHONY: help venv up check seed backfill start demo query verify verify-restart test reset down clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

venv: ## Install Python dependencies
	$(PY) -m pip install -r requirements.txt

up: ## Start local infra (MinIO, Iceberg REST, Trino) and wait until healthy
	$(COMPOSE) up -d
	$(PY) scripts/preflight.py --infra-only --wait 120

check: ## Full preflight: Docker, Atlas, change-stream eligibility, infra
	$(PY) scripts/preflight.py --wait 60

seed: ## Seed historical orders into Atlas (deterministic)
	$(PY) scripts/seed.py

backfill: ## Backfill Atlas history into the Iceberg table
	$(PY) scripts/backfill.py

start: ## Run the Change Streams → Iceberg pipeline in the foreground (Ctrl+C to stop)
	$(PY) scripts/pipeline.py

demo: ## Live story: start pipeline, insert one live order, verify latency
	$(PY) scripts/demo.py

query: ## Run the analytical SQL over Iceberg via Trino
	$(PY) scripts/query.py

verify: ## Verify the last live order is visible in Iceberg + print latency
	$(PY) scripts/verify.py

verify-restart: ## Prove restart safety (no duplicate records)
	$(PY) scripts/verify_restart.py

test: ## Run the automated smoke test
	$(PY) -m pytest tests -v

reset: ## Remove demo data only (Iceberg table, bucket objects, Atlas DB, checkpoints)
	$(PY) scripts/reset.py

down: ## Stop and remove local infra containers
	$(COMPOSE) down

clean: down ## Stop infra AND delete the MinIO volume (full local wipe)
	$(COMPOSE) down -v
