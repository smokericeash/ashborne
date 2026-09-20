from __future__ import annotations

from sqlalchemy import inspect

from app.models import Agent, AuditEvent, Task, TaskStatus
from app.schemas import AgentResponse, AuditResponse, BulkOperationResponse, BulkOperationSummary, TaskResponse


def agent_response(agent: Agent, status=None) -> AgentResponse:
    return AgentResponse(
        id=agent.id,
        agent_id=agent.id,
        name=agent.name,
        hostname=agent.hostname,
        username=agent.username,
        operating_system=agent.operating_system,
        os_version=agent.os_version,
        architecture=agent.architecture,
        ip_address=agent.ip_address,
        agent_version=agent.agent_version,
        first_seen=agent.first_seen,
        last_seen=agent.last_seen,
        status=status or agent.status,
        tags=agent.tags or [],
        uptime_seconds=agent.last_uptime_seconds,
    )


def task_response(task: Task) -> TaskResponse:
    record = task.result_record
    unloaded = inspect(task).unloaded
    agent = None if "agent" in unloaded else task.agent
    requested_by = None if "requested_by" in unloaded else task.requested_by
    return TaskResponse(
        id=task.id,
        agent_id=task.agent_id,
        bulk_operation_id=task.bulk_operation_id,
        agent_name=agent.name if agent else None,
        task_type=task.task_type,
        parameters=task.parameters or {},
        requested_by_id=task.requested_by_id,
        requested_by=requested_by.display_name if requested_by else None,
        requested_by_email=requested_by.email if requested_by else None,
        created_at=task.created_at,
        expires_at=task.expires_at,
        dispatched_at=task.dispatched_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        status=task.status,
        result=record.result if record else None,
        error_message=record.error_message if record else None,
    )


def _bulk_operation_data(tasks: list[Task]) -> dict:
    if not tasks or tasks[0].bulk_operation_id is None:
        raise ValueError("bulk operation requires at least one grouped task")
    first = min(tasks, key=lambda item: item.created_at)
    operation_id = first.bulk_operation_id
    if any(task.bulk_operation_id != operation_id for task in tasks):
        raise ValueError("tasks do not belong to one bulk operation")
    if any(task.task_type != first.task_type or task.parameters != first.parameters for task in tasks):
        raise ValueError("bulk operation tasks have inconsistent configuration")
    unloaded = inspect(first).unloaded
    requested_by = None if "requested_by" in unloaded else first.requested_by
    counts = {status: 0 for status in TaskStatus}
    for task in tasks:
        counts[task.status] += 1
    return {
        "bulk_operation_id": operation_id,
        "task_type": first.task_type,
        "parameters": first.parameters or {},
        "requested_by_id": first.requested_by_id,
        "requested_by": requested_by.display_name if requested_by else None,
        "requested_by_email": requested_by.email if requested_by else None,
        "created_at": first.created_at,
        "target_count": len(tasks),
        "status_counts": counts,
    }


def bulk_operation_summary(tasks: list[Task]) -> BulkOperationSummary:
    return BulkOperationSummary(**_bulk_operation_data(tasks))


def bulk_operation_response(tasks: list[Task]) -> BulkOperationResponse:
    ordered = sorted(tasks, key=lambda item: ((item.agent.name if item.agent else "").casefold(), item.id))
    return BulkOperationResponse(**_bulk_operation_data(ordered), tasks=[task_response(task) for task in ordered])


def audit_response(
    event: AuditEvent,
    *,
    user_email: str | None = None,
    agent_name: str | None = None,
) -> AuditResponse:
    return AuditResponse(
        id=event.id,
        timestamp=event.timestamp,
        event_type=event.event_type,
        user_id=event.user_id,
        user_email=user_email,
        agent_id=event.agent_id,
        agent_name=agent_name,
        source_ip=event.source_ip,
        request_id=event.request_id,
        metadata=event.metadata_ or {},
    )
