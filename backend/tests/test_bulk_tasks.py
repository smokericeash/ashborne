from __future__ import annotations

import uuid

import httpx

from app.core.database import SessionLocal
from app.models import Task
from tests.conftest import authorization
from tests.test_enrollment_agents import create_enrolled_agent, identity


async def enroll_agents(client: httpx.AsyncClient, admin_tokens: dict, count: int = 3) -> list[tuple[dict, dict]]:
    return [await create_enrolled_agent(client, admin_tokens) for _ in range(count)]


async def enroll_kali_controller(client: httpx.AsyncClient, admin_tokens: dict) -> tuple[dict, dict]:
    token = await client.post(
        "/api/v1/enrollment/tokens",
        headers=authorization(admin_tokens),
        json={"expires_in_seconds": 600},
    )
    assert token.status_code == 201, token.text
    payload = identity(ip="10.20.30.5")
    payload.update(
        {
            "name": "kali-controller",
            "hostname": "kali-controller",
            "username": "kali",
            "tags": ["lab", "kali-controller"],
        }
    )
    enrolled = await client.post(
        "/api/v1/enrollment",
        json={**payload, "token": token.json()["token"]},
    )
    assert enrolled.status_code == 201, enrolled.text
    return payload, enrolled.json()


def bulk_payload(agent_ids: list[str], task_type: str = "QUICK_RECON") -> dict:
    return {
        "agent_ids": agent_ids,
        "task_type": task_type,
        "parameters": {},
        "authorized_scope_confirmed": True,
    }


async def create_bulk(
    client: httpx.AsyncClient,
    operator_tokens: dict,
    agent_ids: list[str],
    task_type: str = "QUICK_RECON",
) -> dict:
    response = await client.post(
        "/api/v1/tasks/bulk",
        headers=authorization(operator_tokens),
        json=bulk_payload(agent_ids, task_type),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def finish_task(client: httpx.AsyncClient, enrolled: dict, task_id: str, status: str) -> None:
    headers = {"Authorization": f"Bearer {enrolled['credential']}"}
    agent_id = enrolled["agent"]["agent_id"]
    dispatched = await client.get(f"/api/v1/agents/{agent_id}/tasks", headers=headers)
    assert dispatched.status_code == 200, dispatched.text
    assert task_id in {item["id"] for item in dispatched.json()["items"]}
    started = await client.post(f"/api/v1/tasks/{task_id}/start", headers=headers)
    assert started.status_code == 200, started.text
    submission = (
        {"status": "SUCCESS", "result": {"host": agent_id}}
        if status == "SUCCESS"
        else {"status": "FAILED", "error_message": "bounded observation unavailable"}
    )
    completed = await client.post(f"/api/v1/tasks/{task_id}/result", headers=headers, json=submission)
    assert completed.status_code == 200, completed.text


async def test_bulk_creation_grouping_listing_scope_rbac_and_audit(
    client: httpx.AsyncClient,
    admin_tokens: dict,
    operator_tokens: dict,
    viewer_tokens: dict,
) -> None:
    enrolled = await enroll_agents(client, admin_tokens)
    agent_ids = [payload["agent_id"] for payload, _ in enrolled]
    operator_headers = authorization(operator_tokens)

    unconfirmed = await client.post(
        "/api/v1/tasks/bulk",
        headers=operator_headers,
        json={**bulk_payload(agent_ids), "authorized_scope_confirmed": False},
    )
    assert unconfirmed.status_code == 422
    non_boolean = await client.post(
        "/api/v1/tasks/bulk",
        headers=operator_headers,
        json={**bulk_payload(agent_ids), "authorized_scope_confirmed": 1},
    )
    assert non_boolean.status_code == 422
    duplicate = await client.post(
        "/api/v1/tasks/bulk",
        headers=operator_headers,
        json=bulk_payload([agent_ids[0], agent_ids[0]]),
    )
    assert duplicate.status_code == 422
    forbidden = await client.post(
        "/api/v1/tasks/bulk",
        headers=authorization(viewer_tokens),
        json=bulk_payload(agent_ids),
    )
    assert forbidden.status_code == 403
    missing_target = await client.post(
        "/api/v1/tasks/bulk",
        headers=operator_headers,
        json=bulk_payload([agent_ids[0], str(uuid.uuid4())]),
    )
    assert missing_target.status_code == 404
    no_partial_group = await client.get("/api/v1/tasks/bulk-operations", headers=authorization(viewer_tokens))
    assert no_partial_group.json()["total"] == 0

    operation = await create_bulk(client, operator_tokens, agent_ids)
    operation_id = operation["bulk_operation_id"]
    assert operation["target_count"] == 3
    assert operation["status_counts"] == {
        "QUEUED": 3,
        "DISPATCHED": 0,
        "RUNNING": 0,
        "SUCCESS": 0,
        "FAILED": 0,
        "CANCELLED": 0,
        "TIMED_OUT": 0,
        "EXPIRED": 0,
    }
    assert len({task["id"] for task in operation["tasks"]}) == 3
    assert {task["agent_id"] for task in operation["tasks"]} == set(agent_ids)
    assert {task["bulk_operation_id"] for task in operation["tasks"]} == {operation_id}
    assert {task["requested_by_email"] for task in operation["tasks"]} == {"operator@example.local"}

    async with SessionLocal() as db:
        persisted = [await db.get(Task, item["id"]) for item in operation["tasks"]]
        assert all(task is not None and task.bulk_operation_id == operation_id for task in persisted)

    viewer_headers = authorization(viewer_tokens)
    details = await client.get(f"/api/v1/tasks/bulk-operations/{operation_id}", headers=viewer_headers)
    assert details.status_code == 200, details.text
    listing = await client.get("/api/v1/tasks/bulk-operations", headers=viewer_headers)
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["bulk_operation_id"] == operation_id
    assert "tasks" not in listing.json()["items"][0]

    bulk_audit = await client.get(
        "/api/v1/audit",
        params={"event_type": "BULK_OPERATION_CREATED"},
        headers=authorization(admin_tokens),
    )
    assert bulk_audit.status_code == 200
    assert bulk_audit.json()["total"] == 1
    metadata = bulk_audit.json()["items"][0]["metadata"]
    assert metadata["bulk_operation_id"] == operation_id
    assert metadata["target_count"] == 3
    assert metadata["authorized_scope_confirmed"] is True

    task_audit = await client.get(
        "/api/v1/audit",
        params={"event_type": "TASK_CREATED", "limit": 10},
        headers=authorization(admin_tokens),
    )
    grouped_events = [
        item for item in task_audit.json()["items"] if item["metadata"].get("bulk_operation_id") == operation_id
    ]
    assert len(grouped_events) == 3
    assert all(item["metadata"]["authorized_scope_confirmed"] is True for item in grouped_events)


async def test_bulk_partial_failure_and_retry_failed_only(
    client: httpx.AsyncClient,
    admin_tokens: dict,
    operator_tokens: dict,
    viewer_tokens: dict,
) -> None:
    enrolled = await enroll_agents(client, admin_tokens)
    agent_ids = [payload["agent_id"] for payload, _ in enrolled]
    operation = await create_bulk(client, operator_tokens, agent_ids)
    tasks_by_agent = {task["agent_id"]: task for task in operation["tasks"]}
    await finish_task(client, enrolled[0][1], tasks_by_agent[agent_ids[0]]["id"], "SUCCESS")
    await finish_task(client, enrolled[1][1], tasks_by_agent[agent_ids[1]]["id"], "FAILED")

    operation_id = operation["bulk_operation_id"]
    details = await client.get(f"/api/v1/tasks/bulk-operations/{operation_id}", headers=authorization(operator_tokens))
    assert details.status_code == 200
    assert details.json()["status_counts"]["SUCCESS"] == 1
    assert details.json()["status_counts"]["FAILED"] == 1
    assert details.json()["status_counts"]["QUEUED"] == 1

    for event_type in ("TASK_DISPATCHED", "TASK_STARTED", "TASK_COMPLETED", "TASK_FAILED"):
        lifecycle_audit = await client.get(
            "/api/v1/audit",
            params={"event_type": event_type, "limit": 10},
            headers=authorization(admin_tokens),
        )
        assert lifecycle_audit.status_code == 200
        assert lifecycle_audit.json()["items"]
        assert all(item["metadata"]["bulk_operation_id"] == operation_id for item in lifecycle_audit.json()["items"])

    retry_path = f"/api/v1/tasks/bulk-operations/{operation_id}/retry-failed"
    unconfirmed = await client.post(
        retry_path,
        headers=authorization(operator_tokens),
        json={"authorized_scope_confirmed": False},
    )
    assert unconfirmed.status_code == 422
    forbidden = await client.post(
        retry_path,
        headers=authorization(viewer_tokens),
        json={"authorized_scope_confirmed": True},
    )
    assert forbidden.status_code == 403
    retried = await client.post(
        retry_path,
        headers=authorization(operator_tokens),
        json={"authorized_scope_confirmed": True},
    )
    assert retried.status_code == 201, retried.text
    retry = retried.json()
    assert retry["bulk_operation_id"] != operation_id
    assert retry["target_count"] == 1
    assert retry["tasks"][0]["agent_id"] == agent_ids[1]
    assert retry["tasks"][0]["id"] != tasks_by_agent[agent_ids[1]]["id"]

    none_failed = await client.post(
        f"/api/v1/tasks/bulk-operations/{retry['bulk_operation_id']}/retry-failed",
        headers=authorization(operator_tokens),
        json={"authorized_scope_confirmed": True},
    )
    assert none_failed.status_code == 409

    audit = await client.get(
        "/api/v1/audit",
        params={"event_type": "BULK_OPERATION_RETRIED"},
        headers=authorization(admin_tokens),
    )
    assert audit.json()["total"] == 1
    retry_metadata = audit.json()["items"][0]["metadata"]
    assert retry_metadata["bulk_operation_id"] == retry["bulk_operation_id"]
    assert retry_metadata["source_bulk_operation_id"] == operation_id
    assert retry_metadata["target_count"] == 1


async def test_bulk_cancel_queued_and_rerun_all_targets(
    client: httpx.AsyncClient,
    admin_tokens: dict,
    operator_tokens: dict,
    viewer_tokens: dict,
) -> None:
    enrolled = await enroll_agents(client, admin_tokens)
    agent_ids = [payload["agent_id"] for payload, _ in enrolled]
    operation = await create_bulk(client, operator_tokens, agent_ids, "HOSTNAME")
    operation_id = operation["bulk_operation_id"]
    first_task = next(task for task in operation["tasks"] if task["agent_id"] == agent_ids[0])
    agent_headers = {"Authorization": f"Bearer {enrolled[0][1]['credential']}"}
    dispatched = await client.get(f"/api/v1/agents/{agent_ids[0]}/tasks", headers=agent_headers)
    assert first_task["id"] in {item["id"] for item in dispatched.json()["items"]}

    cancel_path = f"/api/v1/tasks/bulk-operations/{operation_id}/cancel-queued"
    forbidden = await client.post(cancel_path, headers=authorization(viewer_tokens))
    assert forbidden.status_code == 403
    cancelled = await client.post(cancel_path, headers=authorization(operator_tokens))
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status_counts"]["DISPATCHED"] == 1
    assert cancelled.json()["status_counts"]["CANCELLED"] == 2
    assert cancelled.json()["status_counts"]["QUEUED"] == 0

    rerun_path = f"/api/v1/tasks/bulk-operations/{operation_id}/rerun"
    unconfirmed = await client.post(
        rerun_path,
        headers=authorization(operator_tokens),
        json={"authorized_scope_confirmed": False},
    )
    assert unconfirmed.status_code == 422
    rerun = await client.post(
        rerun_path,
        headers=authorization(operator_tokens),
        json={"authorized_scope_confirmed": True},
    )
    assert rerun.status_code == 201, rerun.text
    rerun_body = rerun.json()
    assert rerun_body["bulk_operation_id"] != operation_id
    assert rerun_body["target_count"] == 3
    assert {task["agent_id"] for task in rerun_body["tasks"]} == set(agent_ids)
    assert {task["id"] for task in rerun_body["tasks"].copy()}.isdisjoint({task["id"] for task in operation["tasks"]})

    cancel_audit = await client.get(
        "/api/v1/audit",
        params={"event_type": "BULK_OPERATION_QUEUED_TASKS_CANCELLED"},
        headers=authorization(admin_tokens),
    )
    assert cancel_audit.json()["items"][0]["metadata"]["cancelled_count"] == 2
    rerun_audit = await client.get(
        "/api/v1/audit",
        params={"event_type": "BULK_OPERATION_RERUN"},
        headers=authorization(admin_tokens),
    )
    assert rerun_audit.json()["items"][0]["metadata"]["source_bulk_operation_id"] == operation_id


async def test_new_enumeration_types_are_bounded_no_parameter_actions(
    client: httpx.AsyncClient,
    admin_tokens: dict,
    operator_tokens: dict,
) -> None:
    payload, _ = await create_enrolled_agent(client, admin_tokens)
    task_types = {
        "LINUX_KERNEL_INFO",
        "LINUX_IDENTITY",
        "GROUP_MEMBERSHIP",
        "LINUX_CAPABILITIES",
        "LINUX_MOUNTS",
        "SAFE_ENVIRONMENT_OVERVIEW",
        "SERVICE_OVERVIEW",
        "SCHEDULED_ACTIVITY_OVERVIEW",
        "PRIVILEGE_ENUMERATION",
        "NETWORK_OVERVIEW",
        "HOST_RECON",
    }
    allowlist = await client.get("/api/v1/tasks/allowlist", headers=authorization(operator_tokens))
    assert allowlist.status_code == 200
    assert task_types <= set(allowlist.json())
    for task_type in task_types:
        created = await client.post(
            "/api/v1/tasks",
            headers=authorization(operator_tokens),
            json={
                "agent_id": payload["agent_id"],
                "task_type": task_type,
                "parameters": {},
                "authorized_scope_confirmed": True,
            },
        )
        assert created.status_code == 201, f"{task_type}: {created.text}"
        assert created.json()["parameters"] == {}

    rejected_parameters = await client.post(
        "/api/v1/tasks",
        headers=authorization(operator_tokens),
        json={
            "agent_id": payload["agent_id"],
            "task_type": "HOST_RECON",
            "parameters": {"command": "uname -a"},
            "authorized_scope_confirmed": True,
        },
    )
    assert rejected_parameters.status_code == 422


async def test_kali_operation_routes_through_controller_and_preserves_per_host_results(
    client: httpx.AsyncClient,
    admin_tokens: dict,
    operator_tokens: dict,
) -> None:
    targets = await enroll_agents(client, admin_tokens, count=2)
    controller_payload, controller = await enroll_kali_controller(client, admin_tokens)
    target_ids = [payload["agent_id"] for payload, _ in targets]
    created = await client.post(
        "/api/v1/tasks/bulk",
        headers=authorization(operator_tokens),
        json={
            "agent_ids": target_ids,
            "task_type": "KALI_OPERATION",
            "parameters": {
                "command": "hostname",
                "execution_mode": "ssh",
                "timeout_seconds": 30,
            },
            "authorized_scope_confirmed": True,
        },
    )
    assert created.status_code == 201, created.text
    operation = created.json()
    assert operation["target_count"] == 2
    assert {task["executor_agent_id"] for task in operation["tasks"]} == {
        controller_payload["agent_id"]
    }
    assert {task["target"]["id"] for task in operation["tasks"]} == set(target_ids)

    target_headers = {"Authorization": f"Bearer {targets[0][1]['credential']}"}
    target_poll = await client.get(
        f"/api/v1/agents/{target_ids[0]}/tasks",
        headers=target_headers,
    )
    assert target_poll.status_code == 200
    assert target_poll.json()["items"] == []

    controller_headers = {"Authorization": f"Bearer {controller['credential']}"}
    controller_poll = await client.get(
        f"/api/v1/agents/{controller_payload['agent_id']}/tasks",
        headers=controller_headers,
    )
    assert controller_poll.status_code == 200, controller_poll.text
    tasks = controller_poll.json()["items"]
    assert {task["agent_id"] for task in tasks} == set(target_ids)

    success, timed_out = tasks
    for task in tasks:
        started = await client.post(f"/api/v1/tasks/{task['id']}/start", headers=controller_headers)
        assert started.status_code == 200, started.text
    completed = await client.post(
        f"/api/v1/tasks/{success['id']}/result",
        headers=controller_headers,
        json={
            "status": "SUCCESS",
            "result": {
                "task_type": "KALI_OPERATION",
                "data": {"stdout": "lab-01\n", "stderr": "", "result_code": 0},
            },
        },
    )
    assert completed.status_code == 200, completed.text
    timeout = await client.post(
        f"/api/v1/tasks/{timed_out['id']}/result",
        headers=controller_headers,
        json={
            "status": "TIMED_OUT",
            "result": {
                "task_type": "KALI_OPERATION",
                "data": {"stdout": "", "stderr": "timeout", "result_code": 124},
            },
            "error_message": "operation exceeded its configured timeout",
        },
    )
    assert timeout.status_code == 200, timeout.text

    details = await client.get(
        f"/api/v1/tasks/bulk-operations/{operation['bulk_operation_id']}",
        headers=authorization(operator_tokens),
    )
    assert details.json()["status_counts"]["SUCCESS"] == 1
    assert details.json()["status_counts"]["TIMED_OUT"] == 1
    failed_task = next(task for task in details.json()["tasks"] if task["status"] == "TIMED_OUT")
    assert failed_task["result"]["data"]["stderr"] == "timeout"
    assert failed_task["result"]["data"]["result_code"] == 124

    retried = await client.post(
        f"/api/v1/tasks/bulk-operations/{operation['bulk_operation_id']}/retry-failed",
        headers=authorization(operator_tokens),
        json={"authorized_scope_confirmed": True},
    )
    assert retried.status_code == 201, retried.text
    assert retried.json()["target_count"] == 1
    assert retried.json()["tasks"][0]["agent_id"] == timed_out["agent_id"]
