from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_broker
from app.core.time import utcnow
from app.models import Task, TaskStatus
from app.services.audit import record_audit

ExpiringTask = tuple[str, str]


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
            metadata={"task_id": task.id, "previous": previous.value},
        )
        expired.append((task.id, task.agent_id))
    if expired:
        await db.flush()
    return expired


async def publish_task_expirations(expired: list[ExpiringTask]) -> None:
    for task_id, agent_id in expired:
        await event_broker.publish("task.expired", {"task_id": task_id, "agent_id": agent_id})
