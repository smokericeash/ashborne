from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.events import event_broker
from app.core.time import utcnow
from app.models import Agent, Task, TaskStatus, TaskType, User
from app.services.audit import record_audit

ExpiringTask = tuple[str, str, str | None]


async def load_bulk_operation_tasks(
    db: AsyncSession,
    bulk_operation_id: str,
    *,
    lock: bool = False,
) -> list[Task]:
    statement = (
        select(Task)
        .options(selectinload(Task.result_record), selectinload(Task.agent), selectinload(Task.requested_by))
        .where(Task.bulk_operation_id == bulk_operation_id)
        .order_by(Task.created_at.asc(), Task.id.asc())
    )
    if lock:
        statement = statement.with_for_update()
    return list((await db.execute(statement)).scalars().all())


async def create_bulk_operation_tasks(
    db: AsyncSession,
    *,
    agents: list[Agent],
    task_type: TaskType,
    parameters: dict[str, Any],
    executor_agent_id: str | None,
    actor: User,
    lifetime_seconds: int,
    request: Request,
    audit_event_type: str = "BULK_OPERATION_CREATED",
    source_bulk_operation_id: str | None = None,
) -> tuple[str, list[Task]]:
    """Create one independently addressable task per target under a display-only group id."""

    bulk_operation_id = str(uuid.uuid4())
    now = utcnow()
    tasks: list[Task] = []
    for agent in agents:
        task = Task(
            agent_id=agent.id,
            executor_agent_id=executor_agent_id,
            bulk_operation_id=bulk_operation_id,
            task_type=task_type,
            parameters=parameters.copy(),
            requested_by_id=actor.id,
            created_at=now,
            expires_at=now + timedelta(seconds=lifetime_seconds),
        )
        db.add(task)
        await db.flush()
        await record_audit(
            db,
            "TASK_CREATED",
            request=request,
            user_id=actor.id,
            agent_id=agent.id,
            metadata={
                "task_id": task.id,
                "task_type": task.task_type.value,
                "bulk_operation_id": bulk_operation_id,
                "source_bulk_operation_id": source_bulk_operation_id,
                "authorized_scope_confirmed": True,
            },
        )
        tasks.append(task)
    await record_audit(
        db,
        audit_event_type,
        request=request,
        user_id=actor.id,
        metadata={
            "bulk_operation_id": bulk_operation_id,
            "source_bulk_operation_id": source_bulk_operation_id,
            "task_type": task_type.value,
            "executor_agent_id": executor_agent_id,
            "target_count": len(tasks),
            "authorized_scope_confirmed": True,
        },
    )
    return bulk_operation_id, tasks


async def publish_bulk_operation_created(
    bulk_operation_id: str,
    tasks: list[Task],
    *,
    source_bulk_operation_id: str | None = None,
) -> None:
    for task in tasks:
        await event_broker.publish(
            "task.created",
            {
                "task_id": task.id,
                "agent_id": task.agent_id,
                "task_type": task.task_type.value,
                "bulk_operation_id": bulk_operation_id,
            },
        )
    await event_broker.publish(
        "bulk_operation.created",
        {
            "bulk_operation_id": bulk_operation_id,
            "source_bulk_operation_id": source_bulk_operation_id,
            "task_type": tasks[0].task_type.value,
            "target_count": len(tasks),
        },
    )


async def expire_due_tasks(db: AsyncSession) -> list[ExpiringTask]:
    """Move every overdue non-terminal task to EXPIRED in the current transaction."""

    now = utcnow()
    tasks = (
        (
            await db.execute(
                select(Task)
                .where(
                    Task.expires_at <= now,
                    Task.status.in_([TaskStatus.QUEUED, TaskStatus.DISPATCHED, TaskStatus.RUNNING]),
                )
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    expired: list[ExpiringTask] = []
    for task in tasks:
        previous = task.status
        task.status = TaskStatus.EXPIRED
        task.completed_at = now
        await record_audit(
            db,
            "TASK_EXPIRED",
            agent_id=task.agent_id,
            metadata={
                "task_id": task.id,
                "bulk_operation_id": task.bulk_operation_id,
                "previous": previous.value,
            },
        )
        expired.append((task.id, task.agent_id, task.bulk_operation_id))
    if expired:
        await db.flush()
    return expired


async def publish_task_expirations(expired: list[ExpiringTask]) -> None:
    for task_id, agent_id, bulk_operation_id in expired:
        await event_broker.publish(
            "task.expired",
            {"task_id": task_id, "agent_id": agent_id, "bulk_operation_id": bulk_operation_id},
        )
