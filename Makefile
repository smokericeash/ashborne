.DEFAULT_GOAL := help
.PHONY: help install dev frontend backend test lint format build up down logs reset-db seed demo smoke

PYTHON ?= python
NPM ?= npm
COMPOSE ?= docker compose

help:
	@echo "KANDOR developer commands"
	@echo "  make install    Install all development dependencies"
	@echo "  make backend    Run the FastAPI development server"
	@echo "  make frontend   Run the Vite development server"
	@echo "  make dev        Start the full development stack with Compose"
	@echo "  make test       Run all test suites"
	@echo "  make lint       Run lint and type checks"
	@echo "  make format     Format Python and frontend sources"
	@echo "  make build      Build packages and frontend"
	@echo "  make up/down    Start or stop core containers"
	@echo "  make demo       Start core services and demo agents"
	@echo "  make smoke      Run the API smoke validation"
	@echo "  make reset-db CONFIRM=reset-kandor  Delete local Compose volumes"

install:
	$(PYTHON) -m pip install -e ./backend -r backend/requirements.txt
	$(PYTHON) -m pip install -e "./agent[dev]"
	cd frontend && $(NPM) install

dev: up

backend:
	cd backend && $(PYTHON) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && $(NPM) run dev

test:
	cd backend && $(PYTHON) -m pytest
	cd agent && $(PYTHON) -m pytest
	cd frontend && $(NPM) test -- --run

lint:
	$(PYTHON) scripts/check_allowlist_sync.py
	cd backend && $(PYTHON) -m ruff check app tests
	cd backend && $(PYTHON) -m mypy app
	cd agent && $(PYTHON) -m ruff check kandor_agent tests
	cd agent && $(PYTHON) -m mypy kandor_agent
	cd frontend && $(NPM) run lint
	cd frontend && $(NPM) run typecheck

format:
	cd backend && $(PYTHON) -m ruff format app tests
	cd agent && $(PYTHON) -m ruff format kandor_agent tests
	cd frontend && $(NPM) run format

build:
	$(PYTHON) -m compileall -q backend/app agent/kandor_agent
	cd frontend && $(NPM) run build
	$(COMPOSE) config --quiet

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs --follow --tail=200

seed:
	$(COMPOSE) exec kandor-backend kandor seed

demo:
	$(COMPOSE) --profile demo up --build --scale kandor-agent=5

smoke:
	$(PYTHON) scripts/smoke_test.py

reset-db:
	@if [ "$(CONFIRM)" != "reset-kandor" ]; then echo "Refusing: run make reset-db CONFIRM=reset-kandor"; exit 2; fi
	$(COMPOSE) down --volumes --remove-orphans
