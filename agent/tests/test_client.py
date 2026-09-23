from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx
import pytest

from ashborne_agent.client import (
    AgentAPIError,
    AshborneClient,
    AuthenticationError,
    RetryPolicy,
    enrollment_identity,
)
from ashborne_agent.config import AgentConfig
from ashborne_agent.models import ProtocolError, TaskResult


def json_response(status: int, value: object, request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(value).encode(),
        headers={"content-type": "application/json"},
        request=request,
    )


def test_enrollment_uses_token_without_bearer(agent_config: AgentConfig) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        captured["body"] = json.loads(request.content)
        return json_response(201, {"agent": {}, "credential": "n" * 32}, request)

    with AshborneClient(agent_config, transport=httpx.MockTransport(handler)) as client:
        credential = client.enroll("one-time-token", {"agent_id": agent_config.agent_id})

    request = captured["request"]
    assert credential == "n" * 32
    assert request.url.path == "/api/v1/enrollment"
    assert "authorization" not in request.headers
    assert captured["body"]["token"] == "one-time-token"


def test_demo_enrollment_uses_dedicated_header(agent_config: AgentConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/enrollment/demo"
        assert request.headers["X-Ashborne-Demo-Secret"] == "development-secret"
        assert "token" not in json.loads(request.content)
        return json_response(201, {"credential": "d" * 32}, request)

    with AshborneClient(agent_config, transport=httpx.MockTransport(handler)) as client:
        assert client.enroll_demo("development-secret", {"agent_id": agent_config.agent_id})


def test_reconnect_retries_transport_error(agent_config: AgentConfig) -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("offline", request=request)
        return json_response(200, {"items": [], "count": 0}, request)

    with AshborneClient(
        agent_config,
        transport=httpx.MockTransport(handler),
        sleeper=sleeps.append,
        random_source=lambda: 0,
    ) as client:
        assert client.pending_tasks() == []
    assert calls == 2
    assert sleeps == [0.5]


def test_retryable_api_error_honors_retry_after(agent_config: AgentConfig) -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            response = json_response(503, {"detail": "do not disclose"}, request)
            response.headers["retry-after"] = "1"
            return response
        return json_response(200, {"items": [], "count": 0}, request)

    with AshborneClient(
        agent_config,
        transport=httpx.MockTransport(handler),
        sleeper=sleeps.append,
    ) as client:
        client.pending_tasks()
    assert calls == 3
    assert sleeps == [1.0, 1.0]


def test_nonretryable_api_error_is_sanitized(agent_config: AgentConfig) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return json_response(422, {"detail": "server secret detail"}, request)

    with (
        AshborneClient(agent_config, transport=httpx.MockTransport(handler)) as client,
        pytest.raises(AgentAPIError) as caught,
    ):
        client.pending_tasks()
    assert calls == 1
    assert caught.value.status_code == 422
    assert "server secret detail" not in str(caught.value)


@pytest.mark.parametrize("status", [401, 403])
def test_authentication_failures_are_not_retried(agent_config: AgentConfig, status: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return json_response(status, {}, request)

    with (
        AshborneClient(agent_config, transport=httpx.MockTransport(handler)) as client,
        pytest.raises(AuthenticationError),
    ):
        client.pending_tasks()
    assert calls == 1


def test_authenticated_lifecycle_contract(agent_config: AgentConfig) -> None:
    requests: list[httpx.Request] = []
    task_id = str(uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == f"Bearer {agent_config.credential}"
        if request.url.path.endswith("/heartbeat"):
            return json_response(200, {"status": "ONLINE"}, request)
        if request.url.path.endswith("/tasks"):
            return json_response(
                200,
                {
                    "items": [
                        {
                            "id": task_id,
                            "agent_id": agent_config.agent_id,
                            "task_type": "PING",
                            "parameters": {"message": "hello"},
                        }
                    ],
                    "count": 1,
                },
                request,
            )
        return json_response(200, {"id": task_id}, request)

    with AshborneClient(agent_config, transport=httpx.MockTransport(handler)) as client:
        client.heartbeat({"hostname": "test"})
        task = client.pending_tasks()[0]
        client.start_task(task.id)
        client.submit_result(TaskResult(task.id, "SUCCESS", result={"ok": True}))

    assert [request.url.path for request in requests] == [
        f"/api/v1/agents/{agent_config.agent_id}/heartbeat",
        f"/api/v1/agents/{agent_config.agent_id}/tasks",
        f"/api/v1/tasks/{task_id}/start",
        f"/api/v1/tasks/{task_id}/result",
    ]


def test_controller_accepts_task_for_target_when_it_is_executor(
    agent_config: AgentConfig,
) -> None:
    task_id = str(uuid4())
    target_id = str(uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            200,
            {
                "items": [
                    {
                        "id": task_id,
                        "agent_id": target_id,
                        "executor_agent_id": agent_config.agent_id,
                        "task_type": "KALI_OPERATION",
                        "parameters": {"command": "hostname"},
                        "target": {
                            "id": target_id,
                            "name": "lab-target",
                            "hostname": "lab-target",
                            "username": "lab",
                            "ip_address": "10.0.0.10",
                        },
                    }
                ],
                "count": 1,
            },
            request,
        )

    with AshborneClient(agent_config, transport=httpx.MockTransport(handler)) as client:
        task = client.pending_tasks()[0]

    assert task.agent_id == target_id
    assert task.execution_agent_id == agent_config.agent_id


def test_task_for_another_agent_is_rejected(agent_config: AgentConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            200,
            {
                "items": [
                    {
                        "id": str(uuid4()),
                        "agent_id": str(uuid4()),
                        "task_type": "PING",
                        "parameters": {},
                    }
                ]
            },
            request,
        )

    with (
        AshborneClient(agent_config, transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ProtocolError, match="another execution agent"),
    ):
        client.pending_tasks()


def test_task_for_another_executor_is_rejected(agent_config: AgentConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            200,
            {
                "items": [
                    {
                        "id": str(uuid4()),
                        "agent_id": agent_config.agent_id,
                        "executor_agent_id": str(uuid4()),
                        "task_type": "KALI_OPERATION",
                        "parameters": {"command": "hostname"},
                    }
                ]
            },
            request,
        )

    with (
        AshborneClient(agent_config, transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ProtocolError, match="another execution agent"),
    ):
        client.pending_tasks()


def test_invalid_enrollment_response_is_rejected(agent_config: AgentConfig) -> None:
    transport = httpx.MockTransport(lambda request: json_response(201, {"agent": {}}, request))
    with (
        AshborneClient(agent_config, transport=transport) as client,
        pytest.raises(ProtocolError, match="credential"),
    ):
        client.enroll("token", {"agent_id": agent_config.agent_id})


def test_missing_credential_prevents_authenticated_request(agent_config: AgentConfig) -> None:
    agent_config.credential = None
    with (
        AshborneClient(agent_config, transport=httpx.MockTransport(lambda request: None)) as client,
        pytest.raises(AuthenticationError, match="not enrolled"),
    ):
        client.pending_tasks()


def test_exhausted_retries_raise_connection_error(agent_config: AgentConfig) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("credential=must-not-surface", request=request)

    policy = RetryPolicy(attempts=2, base_delay=0, jitter_ratio=0)
    with (
        AshborneClient(
            agent_config,
            transport=httpx.MockTransport(handler),
            retry_policy=policy,
            sleeper=lambda _delay: None,
        ) as client,
        pytest.raises(AgentAPIError, match="could not connect") as caught,
    ):
        client.pending_tasks()
    assert attempts == 2
    assert "must-not-surface" not in str(caught.value)


@pytest.mark.parametrize(
    "arguments",
    [
        {"attempts": 0},
        {"attempts": True},
        {"base_delay": -1},
        {"base_delay": 2, "maximum_delay": 1},
        {"jitter_ratio": 1.1},
    ],
)
def test_retry_policy_rejects_unsafe_bounds(arguments: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="retry"):
        RetryPolicy(**arguments)  # type: ignore[arg-type]


def test_enrollment_identity_matches_backend_field_bounds(
    agent_config: AgentConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    import getpass
    import platform
    import socket

    uname = platform.uname()
    monkeypatch.setattr(
        platform,
        "uname",
        lambda: uname._replace(system="o" * 121, machine="a" * 65),
    )
    monkeypatch.setattr(platform, "platform", lambda **_kwargs: "v" * 256)
    monkeypatch.setattr(socket, "gethostname", lambda: "h" * 256)
    monkeypatch.setattr(getpass, "getuser", lambda: "u" * 256)
    agent_config.name = "n" * 120

    identity = enrollment_identity(agent_config)

    assert len(identity["name"]) == 120
    assert len(identity["hostname"]) == 255
    assert len(identity["username"]) == 255
    assert len(identity["operating_system"]) == 120
    assert len(identity["os_version"]) == 255
    assert len(identity["architecture"]) == 64
