from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models import AuditEvent

SENSITIVE_KEYS = {"password", "token", "secret", "credential", "authorization", "refresh_token", "access_token"}


def _sanitize(value: Any, depth: int = 0) -> Any:
    if depth > 5:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            str(key)[:80]: "[redacted]" if str(key).lower() in SENSITIVE_KEYS else _sanitize(item, depth + 1)
            for key, item in list(value.items())[:50]
        }
    if isinstance(value, list):
        return [_sanitize(item, depth + 1) for item in value[:50]]
    if isinstance(value, str):
        return value[:1024]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:1024]


async def record_audit(
    db: AsyncSession,
    event_type: str,
    *,
    request: Request | None = None,
    user_id: str | None = None,
    agent_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    source_ip = request.client.host if request and request.client else None
    request_id = getattr(request.state, "request_id", None) if request else None
    event = AuditEvent(
        event_type=event_type,
        user_id=user_id,
        agent_id=agent_id,
        source_ip=source_ip,
        request_id=request_id,
        metadata_=_sanitize(metadata or {}),
    )
    db.add(event)
    await db.flush()
    return event


async def purge_expired_audit_events(db: AsyncSession) -> int:
    """Apply the configured retention policy through the privileged maintenance path."""

    # Import lazily to keep the settings service independent from audit writes.
    from app.services.settings import read_settings

    retention_days = (await read_settings(db)).audit_retention_days
    cutoff = utcnow() - timedelta(days=retention_days)
    result = await db.execute(delete(AuditEvent).where(AuditEvent.timestamp < cutoff))
    deleted = max(0, int(getattr(result, "rowcount", 0) or 0))
    if deleted:
        await record_audit(
            db,
            "AUDIT_RETENTION_PURGED",
            metadata={"deleted": deleted, "cutoff": cutoff.isoformat(), "retention_days": retention_days},
        )
    return deleted
