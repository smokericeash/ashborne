from __future__ import annotations

from sqlalchemy import inspect

from app.models import Agent, AuditEvent, Task
from app.schemas import AgentResponse, AuditResponse, TaskResponse


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
