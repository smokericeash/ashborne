from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.api.dependencies import any_user, get_current_agent, pagination_limit
from app.core.database import get_db
from app.core.events import event_broker
from app.core.time import utcnow
from app.models import Agent, AgentCredential, AgentStatus, Heartbeat, RoleName, Task, TaskStatus, User
from app.schemas import AgentDetail, AgentList, HeartbeatItem, HeartbeatRequest, HeartbeatResponse
from app.services.agents import refresh_agent_statuses
from app.services.audit import record_audit
from app.services.serializers import agent_response, task_response
from app.services.settings import read_settings

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=AgentList)
async def list_agents(
    search: str | None = Query(default=None, max_length=120),
    status_filter: AgentStatus | None = Query(default=None, alias="status"),
    tag: str | None = Query(default=None, min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$"),
    sort_by: str = Query(default="last_seen"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    skip: int = Query(default=0, ge=0),
    limit: int = Depends(pagination_limit),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(any_user),
) -> AgentList:
    changed = await refresh_agent_statuses(db)
    if changed:
        await db.commit()
    filters: list[ColumnElement[bool]] = [Agent.removed_at.is_(None)]
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                Agent.name.ilike(pattern),
                Agent.hostname.ilike(pattern),
                Agent.id.ilike(pattern),
                Agent.username.ilike(pattern),
                Agent.ip_address.ilike(pattern),
                Agent.operating_system.ilike(pattern),
            )
        )
    if status_filter:
        filters.append(Agent.status == status_filter)
    columns = {
        "name": Agent.name,
        "hostname": Agent.hostname,
        "status": Agent.status,
        "first_seen": Agent.first_seen,
        "last_seen": Agent.last_seen,
        "operating_system": Agent.operating_system,
        "agent_version": Agent.agent_version,
    }
    if sort_by not in columns:
        raise HTTPException(status_code=422, detail="unsupported sort field")
    order = columns[sort_by].asc() if sort_order == "asc" else columns[sort_by].desc().nullslast()
    if tag:
        # SQL JSON-array membership is not portable between SQLite and PostgreSQL.
        # Apply the bounded tag comparison before pagination so totals stay exact.
        candidates = (await db.execute(select(Agent).where(*filters).order_by(order))).scalars().all()
        normalized_tag = tag.lower()
        matches = [agent for agent in candidates if normalized_tag in agent.tags]
        total = len(matches)
        rows = matches[skip : skip + limit]
    else:
        total = (await db.execute(select(func.count(Agent.id)).where(*filters))).scalar_one()
        rows = list(
            (await db.execute(select(Agent).where(*filters).order_by(order).offset(skip).limit(limit))).scalars().all()
        )
    return AgentList(items=[agent_response(row) for row in rows], total=total, skip=skip, limit=limit)


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(any_user),
) -> AgentDetail:
    changed = await refresh_agent_statuses(db)
    if changed:
        await db.commit()
    agent = await db.get(Agent, agent_id)
    if not agent or agent.removed_at is not None:
        raise HTTPException(status_code=404, detail="agent not found")
    heartbeats = (
        (
            await db.execute(
                select(Heartbeat).where(Heartbeat.agent_id == agent.id).order_by(Heartbeat.received_at.desc()).limit(20)
            )
        )
        .scalars()
        .all()
    )
    tasks = (
        (
            await db.execute(
                select(Task)
                .options(selectinload(Task.result_record), selectinload(Task.agent), selectinload(Task.requested_by))
                .where(Task.agent_id == agent.id)
                .order_by(Task.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    base = agent_response(agent).model_dump()
    return AgentDetail(
        **base,
        recent_heartbeats=[HeartbeatItem.model_validate(item) for item in heartbeats],
        recent_tasks=[task_response(item) for item in tasks],
    )


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_agent(
    agent_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(any_user),
) -> Response:
    if actor.role != RoleName.ADMINISTRATOR:
        raise HTTPException(status_code=403, detail="administrator role required")
    agent = await db.get(Agent, agent_id)
    if not agent or agent.removed_at is not None:
        raise HTTPException(status_code=404, detail="agent not found")
    now = utcnow()
    agent.removed_at = now
    agent.status = AgentStatus.OFFLINE
    await db.execute(
        update(AgentCredential)
        .where(AgentCredential.agent_id == agent.id, AgentCredential.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.execute(
        update(Task)
        .where(
            Task.agent_id == agent.id,
            Task.status.in_([TaskStatus.QUEUED, TaskStatus.DISPATCHED, TaskStatus.RUNNING]),
        )
        .values(status=TaskStatus.CANCELLED, completed_at=now)
    )
    await record_audit(db, "AGENT_REMOVED", request=request, user_id=actor.id, agent_id=agent.id)
    await db.commit()
    await event_broker.publish("agent.removed", {"agent_id": agent.id})
    return Response(status_code=204)


@router.post("/{agent_id}/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    agent_id: str,
    payload: HeartbeatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    authenticated_agent: Agent = Depends(get_current_agent),
) -> HeartbeatResponse:
    if authenticated_agent.id != agent_id:
        raise HTTPException(status_code=403, detail="agent credential does not match path agent")
    now = utcnow()
    source_ip = request.client.host if request.client else None
    heartbeat_row = Heartbeat(
        agent_id=agent_id,
        received_at=now,
        reported_at=payload.timestamp,
        uptime_seconds=payload.uptime_seconds,
        agent_version=payload.agent_version,
        hostname=payload.hostname,
        ip_address=payload.ip_address or source_ip,
        health=payload.health,
    )
    db.add(heartbeat_row)
    authenticated_agent.last_seen = now
    authenticated_agent.status = AgentStatus.ONLINE
    authenticated_agent.hostname = payload.hostname
    authenticated_agent.agent_version = payload.agent_version
    authenticated_agent.last_uptime_seconds = payload.uptime_seconds
    if payload.ip_address:
        authenticated_agent.ip_address = payload.ip_address
    await record_audit(
        db, "AGENT_HEARTBEAT", request=request, agent_id=agent_id, metadata={"uptime_seconds": payload.uptime_seconds}
    )
    settings = await read_settings(db)
    await db.commit()
    await event_broker.publish(
        "agent.heartbeat", {"agent_id": agent_id, "status": "ONLINE", "last_seen": now.isoformat()}
    )
    return HeartbeatResponse(
        status=AgentStatus.ONLINE, last_seen=now, next_heartbeat_seconds=settings.heartbeat_interval_seconds
    )
