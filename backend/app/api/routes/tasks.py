from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import any_user, get_current_agent, operator_user, pagination_limit
from app.core.database import get_db
from app.core.events import event_broker
from app.core.time import ensure_utc, utcnow
from app.models import Agent, Task, TaskResult, TaskStatus, TaskType, User
from app.schemas import (
    BulkOperationAction,
    BulkOperationList,
    BulkOperationResponse,
    BulkTaskCreate,
    TaskCreate,
    TaskList,
    TaskResponse,
    TaskResultSubmission,
)
from app.services.audit import record_audit
from app.services.serializers import bulk_operation_response, bulk_operation_summary, task_response
from app.services.settings import read_settings
from app.services.tasks import (
    create_bulk_operation_tasks,
    expire_due_tasks,
    load_bulk_operation_tasks,
    publish_bulk_operation_created,
    publish_task_expirations,
)
from app.tasks import validate_task_parameters

router = APIRouter(prefix="/tasks", tags=["tasks"])
TERMINAL_STATUSES = {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.EXPIRED}
DISPATCH_LEASE_SECONDS = 60


async def _load_task(db: AsyncSession, task_id: str, *, lock: bool = False) -> Task:
    statement = (
        select(Task)
        .options(selectinload(Task.result_record), selectinload(Task.agent), selectinload(Task.requested_by))
        .where(Task.id == task_id)
    )
    if lock:
        statement = statement.with_for_update()
    task = (await db.execute(statement)).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


async def _reject_expired_transition(db: AsyncSession, task: Task, request: Request) -> None:
    """Atomically expire overdue work before any user or agent transition."""

    if task.status in TERMINAL_STATUSES or ensure_utc(task.expires_at) > utcnow():
        return
    previous = task.status
    task.status = TaskStatus.EXPIRED
    task.completed_at = utcnow()
    await record_audit(
        db,
        "TASK_EXPIRED",
        request=request,
        agent_id=task.agent_id,
        metadata={"task_id": task.id, "bulk_operation_id": task.bulk_operation_id, "previous": previous.value},
    )
    await db.commit()
    await event_broker.publish(
        "task.expired",
        {"task_id": task.id, "agent_id": task.agent_id, "bulk_operation_id": task.bulk_operation_id},
    )
    raise HTTPException(status_code=409, detail="task has expired")


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(operator_user),
) -> TaskResponse:
    agent = await db.get(Agent, payload.agent_id)
    if not agent or agent.removed_at is not None:
        raise HTTPException(status_code=404, detail="agent not found")
    try:
        parameters = validate_task_parameters(payload.task_type, payload.parameters)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    settings = await read_settings(db)
    lifetime = payload.expires_in_seconds or settings.task_expiration_seconds
    task = Task(
        agent_id=agent.id,
        task_type=payload.task_type,
        parameters=parameters,
        requested_by_id=actor.id,
        expires_at=utcnow() + timedelta(seconds=lifetime),
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
            "authorized_scope_confirmed": payload.authorized_scope_confirmed,
        },
    )
    await db.commit()
    task = await _load_task(db, task.id)
    await event_broker.publish(
        "task.created",
        {
            "task_id": task.id,
            "agent_id": task.agent_id,
            "task_type": task.task_type.value,
            "bulk_operation_id": task.bulk_operation_id,
        },
    )
    return task_response(task)


async def _resolve_agents(db: AsyncSession, agent_ids: list[str]) -> list[Agent]:
    agents = (
        (await db.execute(select(Agent).where(Agent.id.in_(agent_ids), Agent.removed_at.is_(None)))).scalars().all()
    )
    by_id = {agent.id: agent for agent in agents}
    missing = [agent_id for agent_id in agent_ids if agent_id not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"{len(missing)} target agent(s) not found")
    return [by_id[agent_id] for agent_id in agent_ids]


def _ensure_consistent_bulk_operation(tasks: list[Task]) -> None:
    try:
        bulk_operation_summary(tasks)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def _create_bulk_operation(
    *,
    db: AsyncSession,
    request: Request,
    actor: User,
    agents: list[Agent],
    task_type: TaskType,
    parameters: dict[str, Any],
    expires_in_seconds: int | None,
    audit_event_type: str,
    source_bulk_operation_id: str | None = None,
) -> BulkOperationResponse:
    settings = await read_settings(db)
    lifetime = expires_in_seconds or settings.task_expiration_seconds
    operation_id, tasks = await create_bulk_operation_tasks(
        db,
        agents=agents,
        task_type=task_type,
        parameters=parameters,
        actor=actor,
        lifetime_seconds=lifetime,
        request=request,
        audit_event_type=audit_event_type,
        source_bulk_operation_id=source_bulk_operation_id,
    )
    await db.commit()
    tasks = await load_bulk_operation_tasks(db, operation_id)
    await publish_bulk_operation_created(
        operation_id,
        tasks,
        source_bulk_operation_id=source_bulk_operation_id,
    )
    return bulk_operation_response(tasks)


@router.post("/bulk", response_model=BulkOperationResponse, status_code=status.HTTP_201_CREATED)
async def create_bulk_tasks(
    payload: BulkTaskCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(operator_user),
) -> BulkOperationResponse:
    agents = await _resolve_agents(db, payload.agent_ids)
    try:
        parameters = validate_task_parameters(payload.task_type, payload.parameters)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _create_bulk_operation(
        db=db,
        request=request,
        actor=actor,
        agents=agents,
        task_type=payload.task_type,
        parameters=parameters,
        expires_in_seconds=payload.expires_in_seconds,
        audit_event_type="BULK_OPERATION_CREATED",
    )


@router.get("/bulk-operations", response_model=BulkOperationList)
async def list_bulk_operations(
    skip: int = Query(default=0, ge=0),
    limit: int = Depends(pagination_limit),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(any_user),
) -> BulkOperationList:
    expired = await expire_due_tasks(db)
    total = (
        await db.execute(
            select(func.count(func.distinct(Task.bulk_operation_id))).where(Task.bulk_operation_id.is_not(None))
        )
    ).scalar_one()
    operation_rows = (
        await db.execute(
            select(Task.bulk_operation_id, func.min(Task.created_at).label("created_at"))
            .where(Task.bulk_operation_id.is_not(None))
            .group_by(Task.bulk_operation_id)
            .order_by(func.min(Task.created_at).desc())
            .offset(skip)
            .limit(limit)
        )
    ).all()
    operation_ids = [row.bulk_operation_id for row in operation_rows if row.bulk_operation_id is not None]
    grouped: dict[str, list[Task]] = defaultdict(list)
    if operation_ids:
        tasks = (
            (
                await db.execute(
                    select(Task)
                    .options(
                        selectinload(Task.result_record), selectinload(Task.agent), selectinload(Task.requested_by)
                    )
                    .where(Task.bulk_operation_id.in_(operation_ids))
                    .order_by(Task.created_at.asc(), Task.id.asc())
                )
            )
            .scalars()
            .all()
        )
        for task in tasks:
            if task.bulk_operation_id is not None:
                grouped[task.bulk_operation_id].append(task)
    await db.commit()
    await publish_task_expirations(expired)
    return BulkOperationList(
        items=[bulk_operation_summary(grouped[operation_id]) for operation_id in operation_ids],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/bulk-operations/{bulk_operation_id}", response_model=BulkOperationResponse)
async def get_bulk_operation(
    bulk_operation_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(any_user),
) -> BulkOperationResponse:
    expired = await expire_due_tasks(db)
    tasks = await load_bulk_operation_tasks(db, bulk_operation_id)
    if not tasks:
        raise HTTPException(status_code=404, detail="bulk operation not found")
    _ensure_consistent_bulk_operation(tasks)
    await db.commit()
    await publish_task_expirations(expired)
    return bulk_operation_response(tasks)


async def _rerun_bulk_targets(
    *,
    bulk_operation_id: str,
    payload: BulkOperationAction,
    request: Request,
    db: AsyncSession,
    actor: User,
    failed_only: bool,
) -> BulkOperationResponse:
    expired = await expire_due_tasks(db)
    source_tasks = await load_bulk_operation_tasks(db, bulk_operation_id)
    if not source_tasks:
        raise HTTPException(status_code=404, detail="bulk operation not found")
    _ensure_consistent_bulk_operation(source_tasks)
    selected = [task for task in source_tasks if task.status == TaskStatus.FAILED] if failed_only else source_tasks
    if not selected:
        await db.commit()
        await publish_task_expirations(expired)
        raise HTTPException(status_code=409, detail="bulk operation has no failed tasks to retry")
    unique_agent_ids = list(dict.fromkeys(task.agent_id for task in selected))
    agents = await _resolve_agents(db, unique_agent_ids)
    first = source_tasks[0]
    try:
        parameters = validate_task_parameters(first.task_type, first.parameters)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="bulk operation configuration is no longer allowlisted") from exc
    await db.commit()
    await publish_task_expirations(expired)
    return await _create_bulk_operation(
        db=db,
        request=request,
        actor=actor,
        agents=agents,
        task_type=first.task_type,
        parameters=parameters,
        expires_in_seconds=payload.expires_in_seconds,
        audit_event_type="BULK_OPERATION_RETRIED" if failed_only else "BULK_OPERATION_RERUN",
        source_bulk_operation_id=bulk_operation_id,
    )


@router.post(
    "/bulk-operations/{bulk_operation_id}/retry-failed",
    response_model=BulkOperationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def retry_failed_bulk_tasks(
    bulk_operation_id: str,
    payload: BulkOperationAction,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(operator_user),
) -> BulkOperationResponse:
    return await _rerun_bulk_targets(
        bulk_operation_id=bulk_operation_id,
        payload=payload,
        request=request,
        db=db,
        actor=actor,
        failed_only=True,
    )


@router.post(
    "/bulk-operations/{bulk_operation_id}/rerun",
    response_model=BulkOperationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def rerun_bulk_operation(
    bulk_operation_id: str,
    payload: BulkOperationAction,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(operator_user),
) -> BulkOperationResponse:
    return await _rerun_bulk_targets(
        bulk_operation_id=bulk_operation_id,
        payload=payload,
        request=request,
        db=db,
        actor=actor,
        failed_only=False,
    )


@router.post("/bulk-operations/{bulk_operation_id}/cancel-queued", response_model=BulkOperationResponse)
async def cancel_queued_bulk_tasks(
    bulk_operation_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(operator_user),
) -> BulkOperationResponse:
    expired = await expire_due_tasks(db)
    tasks = await load_bulk_operation_tasks(db, bulk_operation_id, lock=True)
    if not tasks:
        raise HTTPException(status_code=404, detail="bulk operation not found")
    _ensure_consistent_bulk_operation(tasks)
    cancelled = [task for task in tasks if task.status == TaskStatus.QUEUED]
    completed_at = utcnow()
    for task in cancelled:
        task.status = TaskStatus.CANCELLED
        task.completed_at = completed_at
        await record_audit(
            db,
            "TASK_CANCELLED",
            request=request,
            user_id=actor.id,
            agent_id=task.agent_id,
            metadata={"task_id": task.id, "bulk_operation_id": bulk_operation_id},
        )
    await record_audit(
        db,
        "BULK_OPERATION_QUEUED_TASKS_CANCELLED",
        request=request,
        user_id=actor.id,
        metadata={"bulk_operation_id": bulk_operation_id, "cancelled_count": len(cancelled)},
    )
    await db.commit()
    tasks = await load_bulk_operation_tasks(db, bulk_operation_id)
    await publish_task_expirations(expired)
    for task in cancelled:
        await event_broker.publish(
            "task.cancelled",
            {"task_id": task.id, "agent_id": task.agent_id, "bulk_operation_id": bulk_operation_id},
        )
    await event_broker.publish(
        "bulk_operation.queued_tasks_cancelled",
        {"bulk_operation_id": bulk_operation_id, "cancelled_count": len(cancelled)},
    )
    return bulk_operation_response(tasks)


@router.get("", response_model=TaskList)
async def list_tasks(
    agent_id: str | None = None,
    search: str | None = Query(default=None, max_length=120),
    task_status: TaskStatus | None = Query(default=None, alias="status"),
    task_type: TaskType | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Depends(pagination_limit),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(any_user),
) -> TaskList:
    expired = await expire_due_tasks(db)
    filters = []
    if agent_id:
        filters.append(Task.agent_id == agent_id)
    if search:
        pattern = f"%{search.strip()}%"
        matching_agents = select(Agent.id).where(
            or_(Agent.id.ilike(pattern), Agent.name.ilike(pattern), Agent.hostname.ilike(pattern))
        )
        filters.append(or_(Task.id.ilike(pattern), Task.agent_id.ilike(pattern), Task.agent_id.in_(matching_agents)))
    if task_status:
        filters.append(Task.status == task_status)
    if task_type:
        filters.append(Task.task_type == task_type)
    total = (await db.execute(select(func.count(Task.id)).where(*filters))).scalar_one()
    rows = (
        (
            await db.execute(
                select(Task)
                .options(selectinload(Task.result_record), selectinload(Task.agent), selectinload(Task.requested_by))
                .where(*filters)
                .order_by(Task.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    await db.commit()
    await publish_task_expirations(expired)
    return TaskList(items=[task_response(row) for row in rows], total=total, skip=skip, limit=limit)


@router.get("/allowlist", response_model=list[str])
async def task_allowlist(_: User = Depends(any_user)) -> list[str]:
    return [item.value for item in TaskType]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(any_user)) -> TaskResponse:
    expired = await expire_due_tasks(db)
    task = await _load_task(db, task_id)
    await db.commit()
    await publish_task_expirations(expired)
    return task_response(task)


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(operator_user),
) -> TaskResponse:
    task = await _load_task(db, task_id, lock=True)
    await _reject_expired_transition(db, task, request)
    if task.status not in {TaskStatus.QUEUED, TaskStatus.DISPATCHED}:
        raise HTTPException(status_code=409, detail="only queued or dispatched tasks can be cancelled")
    task.status = TaskStatus.CANCELLED
    task.completed_at = utcnow()
    await record_audit(
        db,
        "TASK_CANCELLED",
        request=request,
        user_id=actor.id,
        agent_id=task.agent_id,
        metadata={"task_id": task.id, "bulk_operation_id": task.bulk_operation_id},
    )
    await db.commit()
    task = await _load_task(db, task.id)
    await event_broker.publish(
        "task.cancelled",
        {"task_id": task.id, "agent_id": task.agent_id, "bulk_operation_id": task.bulk_operation_id},
    )
    return task_response(task)


@router.post("/{task_id}/start", response_model=TaskResponse)
async def start_task(
    task_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
) -> TaskResponse:
    task = await _load_task(db, task_id, lock=True)
    if task.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="task belongs to a different agent")
    await _reject_expired_transition(db, task, request)
    if task.status == TaskStatus.RUNNING:
        return task_response(task)
    if task.status != TaskStatus.DISPATCHED:
        raise HTTPException(status_code=409, detail=f"task cannot start from {task.status.value}")
    task.status = TaskStatus.RUNNING
    task.started_at = utcnow()
    await record_audit(
        db,
        "TASK_STARTED",
        request=request,
        agent_id=agent.id,
        metadata={"task_id": task.id, "bulk_operation_id": task.bulk_operation_id},
    )
    await db.commit()
    task = await _load_task(db, task.id)
    await event_broker.publish(
        "task.started",
        {"task_id": task.id, "agent_id": task.agent_id, "bulk_operation_id": task.bulk_operation_id},
    )
    return task_response(task)


@router.post("/{task_id}/result", response_model=TaskResponse)
async def submit_result(
    task_id: str,
    payload: TaskResultSubmission,
    request: Request,
    db: AsyncSession = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
) -> TaskResponse:
    task = await _load_task(db, task_id, lock=True)
    if task.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="task belongs to a different agent")
    await _reject_expired_transition(db, task, request)
    requested_status = TaskStatus(payload.status)
    if task.status in {TaskStatus.SUCCESS, TaskStatus.FAILED}:
        if task.status == requested_status:
            return task_response(task)
        raise HTTPException(status_code=409, detail="task already has a different terminal result")
    if task.status != TaskStatus.RUNNING:
        raise HTTPException(status_code=409, detail="task must be running before a result is accepted")
    task.status = requested_status
    task.completed_at = utcnow()
    task.result_record = TaskResult(result=payload.result, error_message=payload.error_message)
    event_type = "TASK_COMPLETED" if requested_status == TaskStatus.SUCCESS else "TASK_FAILED"
    await record_audit(
        db,
        event_type,
        request=request,
        agent_id=agent.id,
        metadata={
            "task_id": task.id,
            "task_type": task.task_type.value,
            "bulk_operation_id": task.bulk_operation_id,
        },
    )
    await db.commit()
    task = await _load_task(db, task.id)
    event_name = "task.succeeded" if requested_status == TaskStatus.SUCCESS else "task.failed"
    await event_broker.publish(
        event_name,
        {"task_id": task.id, "agent_id": task.agent_id, "bulk_operation_id": task.bulk_operation_id},
    )
    return task_response(task)


agent_router = APIRouter(prefix="/agents", tags=["agent tasks"])


@agent_router.get("/{agent_id}/tasks", response_model=TaskList)
async def poll_tasks(
    agent_id: str,
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
) -> TaskList:
    if agent.id != agent_id:
        raise HTTPException(status_code=403, detail="agent credential does not match path agent")
    now = utcnow()
    expired = await expire_due_tasks(db)
    dispatch_cutoff = now - timedelta(seconds=DISPATCH_LEASE_SECONDS)
    tasks = (
        (
            await db.execute(
                select(Task)
                .options(selectinload(Task.result_record), selectinload(Task.agent), selectinload(Task.requested_by))
                .where(
                    Task.agent_id == agent.id,
                    or_(
                        Task.status == TaskStatus.QUEUED,
                        and_(
                            Task.status == TaskStatus.DISPATCHED,
                            or_(Task.dispatched_at.is_(None), Task.dispatched_at <= dispatch_cutoff),
                        ),
                    ),
                    Task.expires_at > now,
                )
                .order_by(Task.created_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for task in tasks:
        redelivered = task.status == TaskStatus.DISPATCHED
        task.status = TaskStatus.DISPATCHED
        task.dispatched_at = now
        await record_audit(
            db,
            "TASK_DISPATCHED",
            request=request,
            agent_id=agent.id,
            metadata={
                "task_id": task.id,
                "bulk_operation_id": task.bulk_operation_id,
                "redelivered": redelivered,
            },
        )
    await db.commit()
    await publish_task_expirations(expired)
    for task in tasks:
        await event_broker.publish(
            "task.dispatched",
            {"task_id": task.id, "agent_id": agent.id, "bulk_operation_id": task.bulk_operation_id},
        )
    return TaskList(
        items=[task_response(task) for task in tasks], total=len(tasks), skip=0, limit=limit, count=len(tasks)
    )
