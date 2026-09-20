from __future__ import annotations

from datetime import timedelta

import httpx

from app.auth.security import decode_token
from app.core.database import SessionLocal
from app.core.time import utcnow
from app.models import AuditEvent, Task
from app.services.audit import purge_expired_audit_events
from tests.conftest import authorization
from tests.test_enrollment_agents import create_enrolled_agent


async def test_task_allowlist_lifecycle_and_result(
    client: httpx.AsyncClient, admin_tokens: dict, operator_tokens: dict
) -> None:
    payload, enrolled = await create_enrolled_agent(client, admin_tokens)
    agent_id = payload["agent_id"]
    operator_auth = authorization(operator_tokens)
    unconfirmed = await client.post(
        "/api/v1/tasks",
        headers=operator_auth,
        json={
            "authorized_scope_confirmed": False,
            "agent_id": agent_id,
            "task_type": "SYSTEM_INFO",
            "parameters": {},
        },
    )
    assert unconfirmed.status_code == 422
    non_boolean_confirmation = await client.post(
        "/api/v1/tasks",
        headers=operator_auth,
        json={
            "authorized_scope_confirmed": 1,
            "agent_id": agent_id,
            "task_type": "SYSTEM_INFO",
            "parameters": {},
        },
    )
    assert non_boolean_confirmation.status_code == 422
    unknown = await client.post(
        "/api/v1/tasks",
        headers=operator_auth,
        json={"authorized_scope_confirmed": True, "agent_id": agent_id, "task_type": "REMOTE_SHELL", "parameters": {}},
    )
    assert unknown.status_code == 422
    arbitrary = await client.post(
        "/api/v1/tasks",
        headers=operator_auth,
        json={
            "authorized_scope_confirmed": True,
            "agent_id": agent_id,
            "task_type": "SYSTEM_INFO",
            "parameters": {"command": "whoami"},
        },
    )
    assert arbitrary.status_code == 422
    invalid_limit = await client.post(
        "/api/v1/tasks",
        headers=operator_auth,
        json={
            "authorized_scope_confirmed": True,
            "agent_id": agent_id,
            "task_type": "PROCESS_INVENTORY",
            "parameters": {"limit": 501},
        },
    )
    assert invalid_limit.status_code == 422

    created = await client.post(
        "/api/v1/tasks",
        headers=operator_auth,
        json={
            "authorized_scope_confirmed": True,
            "agent_id": agent_id,
            "task_type": "PROCESS_INVENTORY",
            "parameters": {"limit": 25},
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    assert created.json()["status"] == "QUEUED"
    assert created.json()["agent_name"] == "lab-node-01"
    assert created.json()["requested_by_email"] == "operator@example.local"
    created_audit = await client.get(
        "/api/v1/audit",
        params={"search": "TASK_CREATED"},
        headers=authorization(admin_tokens),
    )
    assert created_audit.status_code == 200, created_audit.text
    created_events = [
        item
        for item in created_audit.json()["items"]
        if item["event_type"] == "TASK_CREATED" and item["metadata"].get("task_id") == task_id
    ]
    assert created_events
    assert created_events[0]["metadata"]["authorized_scope_confirmed"] is True
    agent_auth = {"Authorization": f"Bearer {enrolled['credential']}"}
    polled = await client.get(f"/api/v1/agents/{agent_id}/tasks", headers=agent_auth)
    assert polled.status_code == 200, polled.text
    assert polled.json()["count"] == 1
    assert polled.json()["items"][0]["status"] == "DISPATCHED"
    immediate_retry = await client.get(f"/api/v1/agents/{agent_id}/tasks", headers=agent_auth)
    assert immediate_retry.status_code == 200
    assert immediate_retry.json()["count"] == 0
    async with SessionLocal() as db:
        dispatched = await db.get(Task, task_id)
        assert dispatched is not None
        dispatched.dispatched_at = utcnow() - timedelta(seconds=61)
        await db.commit()
    redelivered = await client.get(f"/api/v1/agents/{agent_id}/tasks", headers=agent_auth)
    assert redelivered.status_code == 200
    assert [item["id"] for item in redelivered.json()["items"]] == [task_id]
    started = await client.post(f"/api/v1/tasks/{task_id}/start", headers=agent_auth)
    assert started.status_code == 200
    assert started.json()["status"] == "RUNNING"
    completed = await client.post(
        f"/api/v1/tasks/{task_id}/result",
        headers=agent_auth,
        json={"status": "SUCCESS", "result": {"processes": [{"pid": 1, "name": "init"}]}},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "SUCCESS"
    assert completed.json()["result"]["processes"][0]["pid"] == 1
    duplicate = await client.post(
        f"/api/v1/tasks/{task_id}/result",
        headers=agent_auth,
        json={"status": "SUCCESS", "result": {"ignored": True}},
    )
    assert duplicate.status_code == 200

    audit = await client.get(
        "/api/v1/audit",
        params={"agent": "lab-node", "search": "TASK_COMPLETED"},
        headers=authorization(admin_tokens),
    )
    assert audit.status_code == 200, audit.text
    completed_events = [item for item in audit.json()["items"] if item["event_type"] == "TASK_COMPLETED"]
    assert completed_events
    assert completed_events[0]["agent_name"] == "lab-node-01"

    operator_search = await client.get(
        "/api/v1/audit",
        params={"search": "operator@example.local"},
        headers=authorization(admin_tokens),
    )
    assert operator_search.status_code == 200
    assert any(item["user_email"] == "operator@example.local" for item in operator_search.json()["items"])


async def test_task_parameter_defaults_match_agent_protocol(
    client: httpx.AsyncClient, admin_tokens: dict, operator_tokens: dict
) -> None:
    payload, _ = await create_enrolled_agent(client, admin_tokens)
    expected = {
        "PROCESS_INVENTORY": {"limit": 200},
        "INSTALLED_SOFTWARE": {"limit": 300},
        "LISTENING_PORTS": {"limit": 300},
        "NETWORK_CONNECTIONS": {"limit": 200},
        "DISK_USAGE": {"all_partitions": False},
        "PING": {"message": None},
    }
    for task_type, parameters in expected.items():
        created = await client.post(
            "/api/v1/tasks",
            headers=authorization(operator_tokens),
            json={
                "authorized_scope_confirmed": True,
                "agent_id": payload["agent_id"],
                "task_type": task_type,
                "parameters": {},
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["parameters"] == parameters


async def test_viewer_cannot_create_or_cancel_tasks(
    client: httpx.AsyncClient, admin_tokens: dict, viewer_tokens: dict
) -> None:
    payload, _ = await create_enrolled_agent(client, admin_tokens)
    response = await client.post(
        "/api/v1/tasks",
        headers=authorization(viewer_tokens),
        json={
            "authorized_scope_confirmed": True,
            "agent_id": payload["agent_id"],
            "task_type": "SYSTEM_INFO",
            "parameters": {},
        },
    )
    assert response.status_code == 403


async def test_failed_result_validation(client: httpx.AsyncClient, admin_tokens: dict, operator_tokens: dict) -> None:
    payload, enrolled = await create_enrolled_agent(client, admin_tokens)
    created = await client.post(
        "/api/v1/tasks",
        headers=authorization(operator_tokens),
        json={
            "authorized_scope_confirmed": True,
            "agent_id": payload["agent_id"],
            "task_type": "PING",
            "parameters": {"message": "hello"},
        },
    )
    task_id = created.json()["id"]
    agent_auth = {"Authorization": f"Bearer {enrolled['credential']}"}
    await client.get(f"/api/v1/agents/{payload['agent_id']}/tasks", headers=agent_auth)
    await client.post(f"/api/v1/tasks/{task_id}/start", headers=agent_auth)
    invalid = await client.post(
        f"/api/v1/tasks/{task_id}/result", headers=agent_auth, json={"status": "FAILED", "result": {}}
    )
    assert invalid.status_code == 422
    failed = await client.post(
        f"/api/v1/tasks/{task_id}/result",
        headers=agent_auth,
        json={"status": "FAILED", "error_message": "diagnostic unavailable"},
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "FAILED"


async def test_dashboard_settings_and_audit_immutability(client: httpx.AsyncClient, admin_tokens: dict) -> None:
    headers = authorization(admin_tokens)
    metrics = await client.get("/api/v1/dashboard/metrics", headers=headers)
    assert metrics.status_code == 200, metrics.text
    assert metrics.json()["total_agents"] == 0
    assert len(metrics.json()["tasks_over_time"]) == 7
    current = await client.get("/api/v1/settings", headers=headers)
    assert current.status_code == 200
    updated = await client.patch(
        "/api/v1/settings",
        headers=headers,
        json={
            "degraded_threshold_seconds": 90,
            "offline_threshold_seconds": 600,
            "session_timeout_minutes": 37,
            "page_size": 2,
        },
    )
    assert updated.status_code == 200
    default_page = await client.get("/api/v1/users", headers=headers)
    assert default_page.status_code == 200
    assert default_page.json()["limit"] == 2
    assert len(default_page.json()["items"]) == 2
    fresh_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@example.local", "password": "ViewerPassword123!"},
    )
    assert fresh_login.status_code == 200
    claims = decode_token(fresh_login.json()["access_token"], "access")
    assert claims["exp"] - claims["iat"] == 37 * 60
    invalid = await client.patch(
        "/api/v1/settings", headers=headers, json={"degraded_threshold_seconds": 700, "offline_threshold_seconds": 600}
    )
    assert invalid.status_code == 422
    explicit_null = await client.patch("/api/v1/settings", headers=headers, json={"page_size": None})
    assert explicit_null.status_code == 422

    retention = await client.patch("/api/v1/settings", headers=headers, json={"audit_retention_days": 30})
    assert retention.status_code == 200
    old_event_id: str
    async with SessionLocal() as db:
        old_event = AuditEvent(event_type="OLD_TEST_EVENT", timestamp=utcnow() - timedelta(days=31), metadata_={})
        db.add(old_event)
        await db.commit()
        old_event_id = old_event.id
    async with SessionLocal() as db:
        assert await purge_expired_audit_events(db) == 1
        await db.commit()
    async with SessionLocal() as db:
        assert await db.get(AuditEvent, old_event_id) is None
    retention_audit = await client.get(
        "/api/v1/audit",
        params={"event_type": "AUDIT_RETENTION_PURGED"},
        headers=headers,
    )
    assert retention_audit.json()["total"] == 1

    async with SessionLocal() as db:
        event = (await db.execute(__import__("sqlalchemy").select(AuditEvent))).scalars().first()
        assert event is not None
        event.event_type = "TAMPERED"
        try:
            await db.commit()
        except ValueError as exc:
            assert "immutable" in str(exc)
            await db.rollback()
        else:
            raise AssertionError("audit event mutation unexpectedly committed")


async def test_dashboard_expires_stale_running_tasks_with_audit(
    client: httpx.AsyncClient, admin_tokens: dict, operator_tokens: dict
) -> None:
    payload, enrolled = await create_enrolled_agent(client, admin_tokens)
    created = await client.post(
        "/api/v1/tasks",
        headers=authorization(operator_tokens),
        json={
            "authorized_scope_confirmed": True,
            "agent_id": payload["agent_id"],
            "task_type": "PING",
            "parameters": {},
        },
    )
    task_id = created.json()["id"]
    agent_auth = {"Authorization": f"Bearer {enrolled['credential']}"}
    await client.get(f"/api/v1/agents/{payload['agent_id']}/tasks", headers=agent_auth)
    started = await client.post(f"/api/v1/tasks/{task_id}/start", headers=agent_auth)
    assert started.status_code == 200
    async with SessionLocal() as db:
        task = await db.get(Task, task_id)
        assert task is not None
        task.expires_at = utcnow() - timedelta(seconds=1)
        await db.commit()

    metrics = await client.get("/api/v1/dashboard/metrics", headers=authorization(admin_tokens))
    assert metrics.status_code == 200
    assert metrics.json()["tasks_running"] == 0
    expired = await client.get(f"/api/v1/tasks/{task_id}", headers=authorization(admin_tokens))
    assert expired.json()["status"] == "EXPIRED"
    audit = await client.get(
        "/api/v1/audit",
        params={"event_type": "TASK_EXPIRED"},
        headers=authorization(admin_tokens),
    )
    assert any(item["metadata"].get("task_id") == task_id for item in audit.json()["items"])


async def test_overdue_tasks_cannot_transition_before_the_expiration_sweep(
    client: httpx.AsyncClient, admin_tokens: dict, operator_tokens: dict
) -> None:
    payload, enrolled = await create_enrolled_agent(client, admin_tokens)
    agent_id = payload["agent_id"]
    agent_auth = {"Authorization": f"Bearer {enrolled['credential']}"}
    operator_auth = authorization(operator_tokens)
    expired_ids: list[str] = []

    async def create_and_dispatch() -> str:
        created = await client.post(
            "/api/v1/tasks",
            headers=operator_auth,
            json={"authorized_scope_confirmed": True, "agent_id": agent_id, "task_type": "PING", "parameters": {}},
        )
        task_id = created.json()["id"]
        polled = await client.get(f"/api/v1/agents/{agent_id}/tasks", headers=agent_auth)
        assert task_id in {item["id"] for item in polled.json()["items"]}
        return task_id

    async def make_overdue(task_id: str) -> None:
        async with SessionLocal() as db:
            task = await db.get(Task, task_id)
            assert task is not None
            task.expires_at = utcnow() - timedelta(seconds=1)
            await db.commit()

    start_id = await create_and_dispatch()
    await make_overdue(start_id)
    start = await client.post(f"/api/v1/tasks/{start_id}/start", headers=agent_auth)
    assert start.status_code == 409
    expired_ids.append(start_id)

    result_id = await create_and_dispatch()
    started = await client.post(f"/api/v1/tasks/{result_id}/start", headers=agent_auth)
    assert started.status_code == 200
    await make_overdue(result_id)
    result = await client.post(
        f"/api/v1/tasks/{result_id}/result",
        headers=agent_auth,
        json={"status": "SUCCESS", "result": {"pong": True}},
    )
    assert result.status_code == 409
    expired_ids.append(result_id)

    cancel_id = await create_and_dispatch()
    await make_overdue(cancel_id)
    cancelled = await client.post(f"/api/v1/tasks/{cancel_id}/cancel", headers=operator_auth)
    assert cancelled.status_code == 409
    expired_ids.append(cancel_id)

    async with SessionLocal() as db:
        for task_id in expired_ids:
            task = await db.get(Task, task_id)
            assert task is not None
            assert task.status.value == "EXPIRED"

    audit = await client.get(
        "/api/v1/audit",
        params={"event_type": "TASK_EXPIRED", "limit": 10},
        headers=authorization(admin_tokens),
    )
    audited_ids = {item["metadata"].get("task_id") for item in audit.json()["items"]}
    assert set(expired_ids) <= audited_ids
