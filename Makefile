API := apps/api
WEB := apps/web
PY := $(API)/.venv/bin

.PHONY: db db-down api-install api-dev migrate seed test eval sweep lint web-install web-dev web-check check

db:            ## Start local Postgres (host port 5433)
	docker compose up -d db

db-down:
	docker compose down

api-install:   ## Create the API virtualenv and install deps
	cd $(API) && (python3 -m venv .venv || python3 -m virtualenv .venv) && .venv/bin/pip install -e '.[dev]'
	test -f $(API)/.env || cp $(API)/.env.example $(API)/.env

api-dev:       ## Run the API with reload on :8000
	cd $(API) && .venv/bin/uvicorn app.main:app --reload --port 8000

migrate:       ## Apply migrations to the dev database
	cd $(API) && .venv/bin/alembic upgrade head

seed:          ## Seed demo data: make seed EMAIL=you@example.com
	cd $(API) && .venv/bin/python -m app.seed --email $(EMAIL)

test:          ## API tests (needs `make db`)
	cd $(API) && .venv/bin/pytest

eval:          ## AI evals against the real model (costs money; needs ANTHROPIC_API_KEY)
	cd $(API) && ZELA_RUN_EVALS=1 .venv/bin/pytest tests/evals -v

sweep:         ## Re-queue unfinished WhatsApp webhook events
	cd $(API) && .venv/bin/python -m app.workers.sweep

lint:
	cd $(API) && .venv/bin/ruff check . && .venv/bin/ruff format --check .

web-install:
	cd $(WEB) && npm install
	test -f $(WEB)/.env.local || cp $(WEB)/.env.example $(WEB)/.env.local

web-dev:       ## Run the dashboard on :3000
	cd $(WEB) && npm run dev

web-check:
	cd $(WEB) && npm run typecheck && npm run lint && npm run build

check: lint test web-check
