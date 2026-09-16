from __future__ import annotations

import hmac
import secrets
import uuid
from datetime import timedelta
from typing import cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import admin_user, pagination_limit
from app.auth.security import create_opaque_token, sha256
from app.core.config import get_settings
from app.core.database import get_db
from app.core.events import event_broker
from app.core.time import ensure_utc, utcnow
from app.models import Agent, AgentCredential, AgentStatus, EnrollmentToken, User
from app.schemas import (
    AgentEnrollmentResponse,
    AgentEnrollRequest,
    DemoAgentEnrollRequest,
    EnrollmentTokenCreate,
    EnrollmentTokenList,
    EnrollmentTokenResponse,
)
from app.services.audit import record_audit
from app.services.serializers import agent_response

router = APIRouter(prefix="/enrollment", tags=["enrollment"])


def token_view(row: EnrollmentToken, raw_token: str | None = None) -> EnrollmentTokenResponse:
    return EnrollmentTokenResponse(
        id=row.id,
        prefix=row.prefix,
        description=row.description,
        created_by_id=row.created_by_id,
        created_at=row.created_at,
        expires_at=row.expires_at,
        used_at=row.used_at,
        used_by_agent_id=row.used_by_agent_id,
        revoked_at=row.revoked_at,
        token=raw_token,
    )


@router.post("/tokens", response_model=EnrollmentTokenResponse, status_code=status.HTTP_201_CREATED)
async def create_token(
    payload: EnrollmentTokenCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(admin_user),
) -> EnrollmentTokenResponse:
    token_id = str(uuid.uuid4())
    secret = secrets.token_urlsafe(32)
    raw = f"ket_{token_id}.{secret}"
    row = EnrollmentToken(
        id=token_id,
        description=payload.description,
        created_by_id=actor.id,
        expires_at=utcnow() + timedelta(seconds=payload.expires_in_seconds),
        token_hash=sha256(raw),
        prefix=raw[:16],
    )
    db.add(row)
    await db.flush()
    await record_audit(
        db,
        "ENROLLMENT_TOKEN_CREATED",
        request=request,
        user_id=actor.id,
        metadata={"enrollment_token_id": row.id, "expires_at": row.expires_at.isoformat()},
    )
    await db.commit()
    return token_view(row, raw)


@router.get("/tokens", response_model=EnrollmentTokenList)
async def list_tokens(
    skip: int = Query(default=0, ge=0),
    limit: int = Depends(pagination_limit),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(admin_user),
) -> EnrollmentTokenList:
    total = (await db.execute(select(func.count(EnrollmentToken.id)))).scalar_one()
    rows = (
        (
            await db.execute(
                select(EnrollmentToken).order_by(EnrollmentToken.created_at.desc()).offset(skip).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return EnrollmentTokenList(items=[token_view(row) for row in rows], total=total, skip=skip, limit=limit)


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    token_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(admin_user),
) -> Response:
    row = await db.get(EnrollmentToken, token_id)
    if not row:
        raise HTTPException(status_code=404, detail="enrollment token not found")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        await record_audit(
            db,
            "ENROLLMENT_TOKEN_REVOKED",
            request=request,
            user_id=actor.id,
            metadata={"enrollment_token_id": row.id},
        )
        await db.commit()
    return Response(status_code=204)


async def _enroll_agent(
    identity: AgentEnrollRequest | DemoAgentEnrollRequest,
    request: Request,
    db: AsyncSession,
    *,
    allow_reenroll: bool,
    demo: bool,
) -> AgentEnrollmentResponse:
    existing = await db.get(Agent, identity.agent_id)
    now = utcnow()
    if existing and not allow_reenroll:
        raise HTTPException(status_code=409, detail="agent UUID is already enrolled")
    if existing:
        agent = existing
        await db.execute(
            update(AgentCredential)
            .where(AgentCredential.agent_id == agent.id, AgentCredential.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        agent.removed_at = None
        for field in (
            "name",
            "hostname",
            "username",
            "operating_system",
            "os_version",
            "architecture",
            "agent_version",
            "ip_address",
            "tags",
        ):
            setattr(agent, field, getattr(identity, field))
    else:
        agent = Agent(
            id=identity.agent_id,
            name=identity.name or identity.hostname,
            hostname=identity.hostname,
            username=identity.username,
            operating_system=identity.operating_system,
            os_version=identity.os_version,
            architecture=identity.architecture,
            ip_address=identity.ip_address,
            agent_version=identity.agent_version,
            tags=identity.tags,
            first_seen=now,
        )
        db.add(agent)
    agent.last_seen = now
    agent.status = AgentStatus.ONLINE
    raw_credential = create_opaque_token("kac", 36)
    db.add(
        AgentCredential(
            agent_id=agent.id,
            credential_hash=sha256(raw_credential),
            prefix=raw_credential[:16],
        )
    )
    await record_audit(
        db,
        "AGENT_ENROLLED",
        request=request,
        agent_id=agent.id,
        metadata={"demo_bootstrap": demo, "hostname": agent.hostname},
    )
    await db.commit()
    await db.refresh(agent)
    await event_broker.publish("agent.enrolled", {"agent_id": agent.id, "status": agent.status.value})
    return AgentEnrollmentResponse(agent=agent_response(agent), credential=raw_credential)


@router.post("", response_model=AgentEnrollmentResponse, status_code=status.HTTP_201_CREATED)
async def enroll(
    payload: AgentEnrollRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> AgentEnrollmentResponse:
    raw = payload.token.get_secret_value()
    try:
        token_id = raw.split(".", 1)[0].removeprefix("ket_")
        if len(token_id) != 36:
            raise ValueError
    except (ValueError, IndexError):
        raise HTTPException(status_code=401, detail="invalid enrollment token") from None
    row = (
        await db.execute(select(EnrollmentToken).where(EnrollmentToken.id == token_id).with_for_update())
    ).scalar_one_or_none()
    now = utcnow()
    valid = bool(
        row
        and hmac.compare_digest(row.token_hash, sha256(raw))
        and row.used_at is None
        and row.revoked_at is None
        and ensure_utc(row.expires_at) > now
    )
    if not valid:
        await record_audit(
            db, "AGENT_ENROLLMENT_FAILED", request=request, metadata={"reason": "invalid_or_expired_token"}
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="invalid, expired, used, or revoked enrollment token")
    token_row = cast(EnrollmentToken, row)
    token_row.used_at = now
    token_row.used_by_agent_id = payload.agent_id
    response = await _enroll_agent(payload, request, db, allow_reenroll=False, demo=False)
    return response


@router.post("/demo", response_model=AgentEnrollmentResponse, status_code=status.HTTP_201_CREATED)
async def demo_enroll(
    payload: DemoAgentEnrollRequest,
    request: Request,
    x_kandor_demo_secret: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AgentEnrollmentResponse:
    config = get_settings()
    configured = config.demo_bootstrap_secret.get_secret_value() if config.demo_bootstrap_secret else None
    # Test mode exercises the same isolated lab flow; production never exposes it.
    if config.environment not in {"development", "test"} or not configured:
        raise HTTPException(status_code=404, detail="not found")
    if not x_kandor_demo_secret or not hmac.compare_digest(x_kandor_demo_secret, configured):
        await record_audit(db, "DEMO_ENROLLMENT_FAILURE", request=request, metadata={"reason": "invalid_secret"})
        await db.commit()
        raise HTTPException(status_code=401, detail="invalid demo bootstrap credential")
    return await _enroll_agent(payload, request, db, allow_reenroll=True, demo=True)
