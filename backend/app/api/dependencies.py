from __future__ import annotations

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_token, sha256
from app.core.database import get_db
from app.core.time import utcnow
from app.models import Agent, AgentCredential, RoleName, User
from app.services.settings import read_settings

bearer = HTTPBearer(auto_error=False)


def unauthorized(detail: str = "authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    try:
        payload = decode_token(credentials.credentials, "access")
    except jwt.PyJWTError as exc:
        raise unauthorized("invalid or expired access token") from exc
    user = await db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise unauthorized("user is inactive or unavailable")
    if payload.get("role") != user.role.value:
        raise unauthorized("token permissions are stale")
    return user


def require_roles(*allowed: RoleName) -> Callable:
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="insufficient permissions")
        return user

    return dependency


admin_user = require_roles(RoleName.ADMINISTRATOR)
operator_user = require_roles(RoleName.ADMINISTRATOR, RoleName.OPERATOR)
any_user = require_roles(RoleName.ADMINISTRATOR, RoleName.OPERATOR, RoleName.VIEWER)


async def pagination_limit(
    limit: int | None = Query(default=None, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> int:
    if limit is not None:
        return limit
    return (await read_settings(db)).page_size


async def get_current_agent(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> Agent:
    if not credentials or credentials.scheme.lower() != "bearer" or not credentials.credentials.startswith("kac_"):
        raise unauthorized("valid agent credential required")
    digest = sha256(credentials.credentials)
    statement = (
        select(AgentCredential, Agent)
        .join(Agent, Agent.id == AgentCredential.agent_id)
        .where(
            AgentCredential.credential_hash == digest, AgentCredential.revoked_at.is_(None), Agent.removed_at.is_(None)
        )
    )
    row = (await db.execute(statement)).first()
    if not row:
        raise unauthorized("invalid or revoked agent credential")
    credential, agent = row
    credential.last_used_at = utcnow()
    return agent


def request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
