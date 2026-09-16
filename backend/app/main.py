from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import SessionLocal, close_database, create_schema, engine
from app.core.events import event_broker
from app.core.logging import configure_logging
from app.core.middleware import BodyLimitMiddleware, RateLimitMiddleware, RequestIdMiddleware, SecurityHeadersMiddleware
from app.services.agents import refresh_agent_statuses
from app.services.audit import purge_expired_audit_events
from app.services.seed import seed_development
from app.services.tasks import expire_due_tasks, publish_task_expirations

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("kandor.api")


async def _status_monitor(stop: asyncio.Event) -> None:
    interval = max(5, min(settings.heartbeat_interval_seconds, 30))
    next_retention_check = 0.0
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            break
        except TimeoutError:
            pass
        try:
            async with SessionLocal() as db:
                expired = await expire_due_tasks(db)
                statuses_changed = await refresh_agent_statuses(db)
                purged = 0
                if time.monotonic() >= next_retention_check:
                    purged = await purge_expired_audit_events(db)
                    next_retention_check = time.monotonic() + 3600
                if statuses_changed or expired or purged:
                    await db.commit()
                await publish_task_expirations(expired)
        except Exception:
            logger.exception("agent status monitor iteration failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        await create_schema()
    async with SessionLocal() as db:
        created = await seed_development(db, settings)
        if created:
            logger.info("development identities created", extra={"event": "development_seed"})
    stop = asyncio.Event()
    monitor = asyncio.create_task(_status_monitor(stop), name="kandor-agent-status-monitor")
    logger.info("KANDOR API started", extra={"event": "startup"})
    try:
        yield
    finally:
        stop.set()
        monitor.cancel()
        with suppress(asyncio.CancelledError):
            await monitor
        await event_broker.close()
        await close_database()
        logger.info("KANDOR API stopped", extra={"event": "shutdown"})


app = FastAPI(
    title="KANDOR API",
    summary="Self-Hosted Security Agent Orchestration Platform",
    description=(
        "Management API for authenticated users and explicitly enrolled KANDOR agents. "
        "Only allowlisted diagnostic tasks are accepted; arbitrary command execution is intentionally unsupported."
    ),
    version=__version__,
    docs_url=None if settings.environment == "production" else "/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Starlette applies the most recently added middleware first. Add inner layers
# first so request IDs, security headers, and CORS also decorate early rejects.
if settings.trusted_hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
app.add_middleware(
    RateLimitMiddleware,
    requests=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
    login_requests=settings.login_rate_limit_requests,
    redis_url=settings.redis_url,
)
app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_request_bytes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Kandor-Demo-Secret"],
    expose_headers=["X-Request-ID", "Retry-After"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIdMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {"location": list(error["loc"]), "message": error["msg"], "type": error["type"]} for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": "request validation failed", "errors": errors})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Do not serialize exception values here: database/transport exceptions can
    # contain request-derived values. The type and request ID are enough to
    # correlate the sanitized client error with operational telemetry.
    logger.error(
        "unhandled request error",
        extra={"event": "request_error", "exception_type": type(exc).__name__},
    )
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.get("/health/live", tags=["health"])
async def health_live() -> dict[str, str]:
    return {"status": "ok", "service": "kandor-backend", "version": __version__}


@app.get("/health/ready", tags=["health"])
async def health_ready() -> JSONResponse:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unavailable"})
    return JSONResponse(content={"status": "ready", "database": "ok"})


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"name": "KANDOR", "version": __version__, "docs": app.docs_url or app.openapi_url or "disabled"}


app.include_router(api_router)
