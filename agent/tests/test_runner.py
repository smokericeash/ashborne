from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from ashborne_agent.client import AgentAPIError
from ashborne_agent.config import AgentConfig
from ashborne_agent.heartbeat import AgentRunner
from ashborne_agent.models import PendingTask, TaskResult
from ashborne_agent.outbox import ResultOutbox


class FakeClient:
    def __init__(self, tasks: list[PendingTask] | None = None) -> None:
        self.tasks = tasks or []
        self.heartbeats: list[dict[str, Any]] = []
        self.heartbeat_response: dict[str, Any] = {"status": "ONLINE"}
        self.started: list[str] = []
        self.results: list[TaskResult] = []
        self.fail_results = False

    def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.heartbeats.append(payload)
        return self.heartbeat_response

    def pending_tasks(self) -> list[PendingTask]:
        tasks, self.tasks = self.tasks, []
        return tasks

    def start_task(self, task_id: str) -> dict[str, Any]:
        self.started.append(task_id)
        return {"id": task_id}

    def submit_result(self, result: TaskResult) -> dict[str, Any]:
        if self.fail_results:
            raise AgentAPIError("offline", retryable=True)
        self.results.append(result)
        return {"id": result.task_id}


def runner(
    tmp_path: Path,
    agent_config: AgentConfig,
    client: FakeClient,
    *,
    clock: Any = lambda: 0,
) -> AgentRunner:
    return AgentRunner(
        agent_config,
        client,  # type: ignore[arg-type]
        ResultOutbox(tmp_path / "outbox.json"),
        monotonic=clock,
    )


def test_successful_task_lifecycle(tmp_path: Path, agent_config: AgentConfig) -> None:
    task = PendingTask(str(uuid4()), agent_config.agent_id, "PING", {"message": "hello"})
    client = FakeClient([task])
    service = runner(tmp_path, agent_config, client)

    service.run_cycle()

    assert len(client.heartbeats) == 1
    assert client.started == [task.id]
    assert client.results[0].status == "SUCCESS"
    assert client.results[0].result is not None
    assert client.results[0].result["data"]["pong"] is True
    assert service.outbox.items == ()


def test_invalid_task_is_started_then_reported_failed(
    tmp_path: Path, agent_config: AgentConfig
) -> None:
    task = PendingTask(str(uuid4()), agent_config.agent_id, "SHELL", {"command": "id"})
    client = FakeClient([task])
    service = runner(tmp_path, agent_config, client)

    service.run_cycle()

    assert client.started == [task.id]
    assert client.results[0].status == "FAILED"
    assert "allowlisted" in (client.results[0].error_message or "")
    assert "id" not in (client.results[0].error_message or "")


def test_result_is_durable_when_submission_fails(tmp_path: Path, agent_config: AgentConfig) -> None:
    task = PendingTask(str(uuid4()), agent_config.agent_id, "HOSTNAME", {})
    client = FakeClient()
    client.fail_results = True
    service = runner(tmp_path, agent_config, client)

    with pytest.raises(AgentAPIError):
        service.process_task(task)

    reloaded = ResultOutbox(tmp_path / "outbox.json")
    assert len(reloaded.items) == 1
    assert reloaded.items[0].task_id == task.id


def test_queued_result_is_flushed_after_reconnect(
    tmp_path: Path, agent_config: AgentConfig
) -> None:
    task_id = str(uuid4())
    outbox = ResultOutbox(tmp_path / "outbox.json")
    outbox.enqueue(TaskResult(task_id, "SUCCESS", result={"ok": True}))
    client = FakeClient()
    service = AgentRunner(agent_config, client, outbox)  # type: ignore[arg-type]

    service.flush_outbox()

    assert [result.task_id for result in client.results] == [task_id]
    assert outbox.items == ()


def test_heartbeat_respects_interval(tmp_path: Path, agent_config: AgentConfig) -> None:
    values = iter([0.0, 10.0, 30.0])
    client = FakeClient()
    service = runner(tmp_path, agent_config, client, clock=lambda: next(values))

    service.run_cycle()
    service.run_cycle()
    service.run_cycle()

    assert len(client.heartbeats) == 2


def test_heartbeat_honors_valid_server_interval(tmp_path: Path, agent_config: AgentConfig) -> None:
    values = iter([0.0, 9.0, 10.0])
    client = FakeClient()
    client.heartbeat_response["next_heartbeat_seconds"] = 10.0
    service = runner(tmp_path, agent_config, client, clock=lambda: next(values))

    service.run_cycle()
    service.run_cycle()
    service.run_cycle()

    assert len(client.heartbeats) == 2
    assert agent_config.heartbeat_interval == 30


@pytest.mark.parametrize("invalid", [True, "10", 4, 3601, float("nan")])
def test_invalid_server_heartbeat_interval_uses_local_config(
    tmp_path: Path, agent_config: AgentConfig, invalid: object
) -> None:
    client = FakeClient()
    client.heartbeat_response["next_heartbeat_seconds"] = invalid
    service = runner(tmp_path, agent_config, client)

    service.run_cycle()

    assert service._next_heartbeat == agent_config.heartbeat_interval


def test_cross_agent_task_is_never_started(tmp_path: Path, agent_config: AgentConfig) -> None:
    task = PendingTask(str(uuid4()), str(uuid4()), "PING", {})
    client = FakeClient()
    service = runner(tmp_path, agent_config, client)

    with pytest.raises(ValueError, match="another agent"):
        service.process_task(task)
    assert client.started == []
    assert client.results == []


def test_kali_controller_routes_parallel_results_per_target(
    tmp_path: Path,
    agent_config: AgentConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_config.kali_controller = True
    agent_config.max_parallel_hosts = 2
    targets = [str(uuid4()), str(uuid4())]
    tasks = [
        PendingTask(
            str(uuid4()),
            target_id,
            "KALI_OPERATION",
            {"command": "hostname", "execution_mode": "ssh", "timeout_seconds": 5},
            agent_config.agent_id,
            {
                "id": target_id,
                "name": f"target-{index}",
                "hostname": f"target-{index}",
                "username": "lab",
                "ip_address": f"10.0.0.{index + 10}",
            },
        )
        for index, target_id in enumerate(targets)
    ]

    def fake_execute(_parameters: object, target: object) -> dict[str, Any]:
        assert isinstance(target, dict)
        return {
            "task_type": "KALI_OPERATION",
            "collected_at": "2026-09-20T00:00:00Z",
            "data": {
                "stdout": target["hostname"],
                "stderr": "",
                "result_code": 0,
                "timed_out": False,
            },
        }

    monkeypatch.setattr("ashborne_agent.heartbeat.execute_operation", fake_execute)
    client = FakeClient(tasks)
    service = runner(tmp_path, agent_config, client)

    service.run_cycle()

    assert set(client.started) == {task.id for task in tasks}
    assert {result.status for result in client.results} == {"SUCCESS"}
    assert {result.result["data"]["stdout"] for result in client.results if result.result} == {
        "target-0",
        "target-1",
    }
