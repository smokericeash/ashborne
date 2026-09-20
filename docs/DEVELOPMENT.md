# ASHBORNE developer guide

## Prerequisites

- Python 3.12 with `venv`
- Node.js 22.12 or newer and npm
- Docker with Compose v2
- GNU Make (optional convenience wrapper)

## Backend

Create a virtual environment, install `backend` development dependencies, configure a test or local database URL, run Alembic, then start Uvicorn. Tests default to an isolated SQLite database where supported and integration runs exercise PostgreSQL in CI.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend && alembic upgrade head && uvicorn app.main:app --reload
```

On PowerShell activate with `.venv\Scripts\Activate.ps1`.

## Frontend

```bash
cd frontend
npm ci
npm run dev
```

Vite proxies API and event requests to the development backend. Keep generated API-facing TypeScript types aligned with Pydantic/OpenAPI contracts.

## Agent

```bash
python -m pip install -e "./agent[dev]"
pytest agent/tests
```

Use a disposable container or test VM for manual inventory checks. Never add a generic subprocess, interpreter, script, or file-execution escape hatch.

## Definition of done

- Behavior, negative authorization, invalid input, and audit side effects have tests.
- Database changes include an Alembic revision and index review.
- `make format`, `make lint`, `make test`, and `make build` pass.
- `docker compose config --quiet` and container builds pass.
- The demo smoke flow confirms login, metrics, enrollment, heartbeat, task/result, RBAC, unknown-task rejection, and audit visibility.
- Documentation and `.env.example` reflect new settings without containing a real secret.
