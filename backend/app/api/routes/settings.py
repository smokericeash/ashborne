from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import admin_user, any_user
from app.core.database import get_db
from app.models import User
from app.schemas import SettingsResponse, SettingsUpdate
from app.services.audit import record_audit
from app.services.settings import read_settings, update_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
async def get_application_settings(db: AsyncSession = Depends(get_db), _: User = Depends(any_user)) -> SettingsResponse:
    return await read_settings(db)


@router.patch("", response_model=SettingsResponse)
async def patch_application_settings(
    payload: SettingsUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(admin_user),
) -> SettingsResponse:
    changes = payload.model_dump(exclude_unset=True)
    try:
        response = await update_settings(db, changes, actor.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await record_audit(db, "SETTINGS_UPDATED", request=request, user_id=actor.id, metadata={"keys": sorted(changes)})
    await db.commit()
    return response
