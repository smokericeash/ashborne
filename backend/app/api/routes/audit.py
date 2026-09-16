from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import any_user, pagination_limit
from app.core.database import get_db
from app.core.time import ensure_utc
from app.models import Agent, AuditEvent, User
from app.schemas import AuditList
from app.services.serializers import audit_response

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditList)
async def list_audit_events(
    user_id: str | None = None,
    agent_id: str | None = None,
    user: str | None = Query(default=None, max_length=120),
    agent: str | None = Query(default=None, max_length=120),
    search: str | None = Query(default=None, max_length=120),
    event_type: str | None = Query(default=None, max_length=80),
    source_ip: str | None = Query(default=None, max_length=45),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Depends(pagination_limit),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(any_user),
) -> AuditList:
    filters = []
    if user_id:
        filters.append(AuditEvent.user_id == user_id)
    if agent_id:
        filters.append(AuditEvent.agent_id == agent_id)
    if user:
        pattern = f"%{user.strip()}%"
        matching_users = select(User.id).where(
            or_(User.id.ilike(pattern), User.email.ilike(pattern), User.display_name.ilike(pattern))
        )
        filters.append(AuditEvent.user_id.in_(matching_users))
    if agent:
        pattern = f"%{agent.strip()}%"
        matching_agents = select(Agent.id).where(
            or_(
                Agent.id.ilike(pattern),
                Agent.name.ilike(pattern),
                Agent.hostname.ilike(pattern),
                Agent.ip_address.ilike(pattern),
            )
        )
        filters.append(AuditEvent.agent_id.in_(matching_agents))
    if search:
        pattern = f"%{search.strip()}%"
        matching_users = select(User.id).where(
            or_(User.id.ilike(pattern), User.email.ilike(pattern), User.display_name.ilike(pattern))
        )
        matching_agents = select(Agent.id).where(
            or_(
                Agent.id.ilike(pattern),
                Agent.name.ilike(pattern),
                Agent.hostname.ilike(pattern),
                Agent.ip_address.ilike(pattern),
            )
        )
        filters.append(
            or_(
                AuditEvent.id.ilike(pattern),
                AuditEvent.event_type.ilike(pattern),
                AuditEvent.request_id.ilike(pattern),
                AuditEvent.source_ip.ilike(pattern),
                cast(AuditEvent.metadata_, Text).ilike(pattern),
                AuditEvent.user_id.in_(matching_users),
                AuditEvent.agent_id.in_(matching_agents),
            )
        )
    if event_type:
        filters.append(AuditEvent.event_type == event_type.upper())
    if source_ip:
        filters.append(AuditEvent.source_ip == source_ip)
    if start_time and end_time and ensure_utc(start_time) > ensure_utc(end_time):
        raise HTTPException(status_code=422, detail="start_time must not be later than end_time")
    if start_time:
        filters.append(AuditEvent.timestamp >= ensure_utc(start_time))
    if end_time:
        filters.append(AuditEvent.timestamp <= ensure_utc(end_time))
    total = (await db.execute(select(func.count(AuditEvent.id)).where(*filters))).scalar_one()
    rows = (
        await db.execute(
            select(AuditEvent, User.email, Agent.name)
            .outerjoin(User, User.id == AuditEvent.user_id)
            .outerjoin(Agent, Agent.id == AuditEvent.agent_id)
            .where(*filters)
            .order_by(AuditEvent.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )
    ).all()
    return AuditList(
        items=[audit_response(row, user_email=email, agent_name=name) for row, email, name in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/event-types", response_model=list[str])
async def event_types(db: AsyncSession = Depends(get_db), _: User = Depends(any_user)) -> list[str]:
    return list(
        (await db.execute(select(AuditEvent.event_type).distinct().order_by(AuditEvent.event_type))).scalars().all()
    )
