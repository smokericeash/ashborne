from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Setting
from app.schemas import SettingsResponse

SETTING_KEYS = {
    "heartbeat_interval_seconds",
    "degraded_threshold_seconds",
    "offline_threshold_seconds",
    "task_expiration_seconds",
    "session_timeout_minutes",
    "page_size",
    "audit_retention_days",
}


def config_defaults() -> dict[str, Any]:
    config = get_settings()
    return {
        "heartbeat_interval_seconds": config.heartbeat_interval_seconds,
        "degraded_threshold_seconds": config.degraded_threshold_seconds,
        "offline_threshold_seconds": config.offline_threshold_seconds,
        "task_expiration_seconds": config.task_expiration_seconds,
        "session_timeout_minutes": config.session_timeout_minutes,
        "page_size": config.page_size,
        "audit_retention_days": config.audit_retention_days,
    }


async def read_settings(db: AsyncSession) -> SettingsResponse:
    values = config_defaults()
    rows = (await db.execute(select(Setting).where(Setting.key.in_(SETTING_KEYS)))).scalars().all()
    values.update({row.key: row.value for row in rows})
    return SettingsResponse.model_validate(values)


async def update_settings(db: AsyncSession, values: dict[str, Any], user_id: str) -> SettingsResponse:
    current = await read_settings(db)
    merged = current.model_dump()
    merged.update(values)
    if merged["degraded_threshold_seconds"] >= merged["offline_threshold_seconds"]:
        raise ValueError("degraded threshold must be lower than offline threshold")
    for key, value in values.items():
        row = await db.get(Setting, key)
        if row:
            row.value = value
            row.updated_by_id = user_id
        else:
            db.add(Setting(key=key, value=value, updated_by_id=user_id))
    await db.flush()
    return SettingsResponse.model_validate(merged)
