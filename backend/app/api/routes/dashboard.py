from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import TypedDict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import any_user
from app.core.database import get_db
from app.core.time import ensure_utc, utcnow
from app.models import Agent, AgentStatus, AuditEvent, Heartbeat, Task, TaskStatus, User
from app.schemas import ActivityResponse, DashboardMetrics
from app.services.agents import refresh_agent_statuses
from app.services.serializers import agent_response, audit_response, task_response
from app.services.tasks import expire_due_tasks, publish_task_expirations

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class TaskDay(TypedDict):
    date: str
    success: int
    failed: int
    created: int


class HeartbeatDay(TypedDict):
    date: str
    count: int


@router.get("/metrics", response_model=DashboardMetrics)
async def metrics(db: AsyncSession = Depends(get_db), _: User = Depends(any_user)) -> DashboardMetrics:
    expired = await expire_due_tasks(db)
    changed = await refresh_agent_statuses(db)
    agents = (await db.execute(select(Agent).where(Agent.removed_at.is_(None)))).scalars().all()
    tasks = (
        (
            await db.execute(
                select(Task).options(
                    selectinload(Task.result_record), selectinload(Task.agent), selectinload(Task.requested_by)
                )
            )
        )
        .scalars()
        .all()
    )
    now = utcnow()
    since = now - timedelta(days=7)
    heartbeats = (
        (
            await db.execute(
                select(Heartbeat)
                .where(Heartbeat.received_at >= since)
                .order_by(Heartbeat.agent_id, Heartbeat.received_at)
            )
        )
        .scalars()
        .all()
    )
    if changed or expired:
        await db.commit()
    await publish_task_expirations(expired)

    status_counts = Counter(agent.status.value for agent in agents)
    task_counts = Counter(task.status.value for task in tasks)
    successful = task_counts[TaskStatus.SUCCESS.value]
    failed = task_counts[TaskStatus.FAILED.value]
    finished = successful + failed
    os_distribution = Counter(agent.operating_system for agent in agents)
    version_distribution = Counter(agent.agent_version for agent in agents)

    task_days: dict[str, TaskDay] = {}
    for offset in range(6, -1, -1):
        date = (now - timedelta(days=offset)).date().isoformat()
        task_days[date] = {"date": date, "success": 0, "failed": 0, "created": 0}
    for task in tasks:
        date = ensure_utc(task.created_at).date().isoformat()
        if date in task_days:
            task_days[date]["created"] += 1
            if task.status == TaskStatus.SUCCESS:
                task_days[date]["success"] += 1
            elif task.status == TaskStatus.FAILED:
                task_days[date]["failed"] += 1

    heartbeat_days: dict[str, HeartbeatDay] = {date: {"date": date, "count": 0} for date in task_days}
    intervals: list[float] = []
    previous_by_agent: dict[str, datetime] = {}
    for item in heartbeats:
        received = ensure_utc(item.received_at)
        date = received.date().isoformat()
        if date in heartbeat_days:
            heartbeat_days[date]["count"] += 1
        previous = previous_by_agent.get(item.agent_id)
        if previous:
            interval = (received - previous).total_seconds()
            if 0 <= interval <= 86_400:
                intervals.append(interval)
        previous_by_agent[item.agent_id] = received

    return DashboardMetrics(
        total_agents=len(agents),
        online_agents=status_counts[AgentStatus.ONLINE.value],
        degraded_agents=status_counts[AgentStatus.DEGRADED.value],
        offline_agents=status_counts[AgentStatus.OFFLINE.value],
        tasks_queued=task_counts[TaskStatus.QUEUED.value] + task_counts[TaskStatus.DISPATCHED.value],
        tasks_running=task_counts[TaskStatus.RUNNING.value],
        tasks_completed=finished,
        tasks_failed=failed,
        task_success_rate=round(successful / finished * 100, 2) if finished else 0.0,
        average_checkin_interval_seconds=round(sum(intervals) / len(intervals), 2) if intervals else None,
        os_distribution=dict(os_distribution),
        version_distribution=dict(version_distribution),
        tasks_over_time=list(task_days.values()),
        heartbeat_activity=list(heartbeat_days.values()),
    )


@router.get("/activity", response_model=ActivityResponse)
async def activity(db: AsyncSession = Depends(get_db), _: User = Depends(any_user)) -> ActivityResponse:
    expired = await expire_due_tasks(db)
    agents = (
        (await db.execute(select(Agent).where(Agent.removed_at.is_(None)).order_by(Agent.last_seen.desc()).limit(10)))
        .scalars()
        .all()
    )
    tasks = (
        (
            await db.execute(
                select(Task)
                .options(selectinload(Task.result_record), selectinload(Task.agent), selectinload(Task.requested_by))
                .order_by(Task.created_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    audits = (await db.execute(select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(10))).scalars().all()
    if expired:
        await db.commit()
    await publish_task_expirations(expired)
    return ActivityResponse(
        agents=[agent_response(item) for item in agents],
        tasks=[task_response(item) for item in tasks],
        audit_events=[audit_response(item) for item in audits],
    )
