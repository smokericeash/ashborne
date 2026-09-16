from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from app.api.dependencies import bearer, unauthorized
from app.auth.security import decode_token
from app.core.database import SessionLocal
from app.core.events import event_broker
from app.models import User

router = APIRouter(prefix="/events", tags=["events"])


async def _stream_user_is_current(user_id: str, role: str) -> bool:
    async with SessionLocal() as db:
        user = await db.get(User, user_id)
        return bool(user and user.is_active and user.role.value == role)


@router.get("/stream")
async def stream_events(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> StreamingResponse:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    try:
        claims = decode_token(credentials.credentials, "access")
        user_id = str(claims["sub"])
        role = str(claims["role"])
        expires_at = datetime.fromtimestamp(int(claims["exp"]), UTC)
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise unauthorized("invalid or expired access token") from exc
    if not await _stream_user_is_current(user_id, role):
        raise unauthorized("user is inactive or token permissions are stale")

    async def generate():
        last_authorization_check = time.monotonic()
        async for event in event_broker.subscribe():
            if datetime.now(UTC) >= expires_at:
                break
            if time.monotonic() - last_authorization_check >= 15:
                if not await _stream_user_is_current(user_id, role):
                    break
                last_authorization_check = time.monotonic()
            yield f"event: {event['event']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
