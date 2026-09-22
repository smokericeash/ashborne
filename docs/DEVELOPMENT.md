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

### Frontend performance notes

The bulk-operations work included a build-output and render-path review before changing the frontend:

- The earlier production build eagerly included every page and produced about 764 KB of startup JavaScript across the 173.5 KB application entry, 495.0 KB chart chunk, 62.8 KB D3 chunk, and 32.2 KB icon chunk.
- The current build lazy-loads route pages. Its HTML initially references 278.3 KB of JavaScript (245.1 KB application entry plus 33.2 KB icons, 87.8 KB gzip); route chunks are loaded on demand and range from 1.6 KB to 17.8 KB. The simplified Command Center no longer ships the unused chart/D3 payload.
- One centralized SSE connection remains authoritative, but event-family contexts now invalidate only the host, task, audit, or dashboard consumers that need that event. This avoids unrelated page reloads and rerenders.
- Host search is debounced, concurrent identical GET requests share one in-flight promise, table sorting/filtering is memoized where it is client-side, callbacks and selection state are stable, and result cards are memoized.
- Host and task APIs remain server-paginated. Bulk dispatch is capped at 100 hosts, so table virtualization would add complexity without improving the measured bounded views; revisit it only if those limits change.

Re-run `npm run build` after material UI dependency or routing changes and compare both the initial HTML dependencies and route-chunk sizes, not only the largest generated file.

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
