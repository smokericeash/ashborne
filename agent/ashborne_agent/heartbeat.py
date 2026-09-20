"""Agent heartbeat, polling, execution, and durable result lifecycle."""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable

from ashborne_agent.client import (
    AgentAPIError,
    AshborneClient,
    AuthenticationError,
    heartbeat_payload,
)
from ashborne_agent.config import AgentConfig
from ashborne_agent.executor import TaskExecutionError, TaskValidationError, execute_task
from ashborne_agent.models import PendingTask, ProtocolError, TaskResult
from ashborne_agent.outbox import ResultOutbox

LOG = logging.getLogger("ashborne_agent.runner")
MAX_TASKS_PER_CYCLE = 10


class AgentRunner:
    def __init__(
        self,
        config: AgentConfig,
        client: AshborneClient,
        outbox: ResultOutbox,
        *,
        stop_event: threading.Event | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.client = client
        self.outbox = outbox
        self.stop_event = stop_event or threading.Event()
        self._monotonic = monotonic
        self._next_heartbeat = 0.0
        self._failure_count = 0

    def run_forever(self) -> None:
        LOG.info(
            "ASHBORNE agent started",
            extra={"event": "agent_started", "agent_id": self.config.agent_id},
        )
        while not self.stop_event.is_set():
            try:
                self.run_cycle()
                self._failure_count = 0
                self.stop_event.wait(self.config.poll_interval)
            except AuthenticationError:
                LOG.error(
                    "Agent authentication failed; re-enrollment is required",
                    extra={"event": "authentication_failed", "agent_id": self.config.agent_id},
                )
                raise
            except (AgentAPIError, ProtocolError) as exc:
                self._failure_count += 1
                delay = min(60.0, max(self.config.poll_interval, 2 ** min(self._failure_count, 6)))
                LOG.warning(
                    "ASHBORNE API unavailable; agent will reconnect",
                    extra={
                        "event": "reconnect_wait",
                        "agent_id": self.config.agent_id,
                        "delay_seconds": delay,
                        "error_type": type(exc).__name__,
                    },
                )
                self.stop_event.wait(delay)
        LOG.info(
            "ASHBORNE agent stopped",
            extra={"event": "agent_stopped", "agent_id": self.config.agent_id},
        )

    def run_cycle(self) -> None:
        now = self._monotonic()
        if now >= self._next_heartbeat:
            response = self.client.heartbeat(heartbeat_payload())
            interval = self._heartbeat_interval(response)
            self._next_heartbeat = now + interval
            LOG.info(
                "Heartbeat accepted",
                extra={
                    "event": "heartbeat_sent",
                    "agent_id": self.config.agent_id,
                    "next_heartbeat_seconds": interval,
                },
            )

        self.flush_outbox()
        tasks = self.client.pending_tasks()
        for task in tasks[:MAX_TASKS_PER_CYCLE]:
            if self.stop_event.is_set():
                break
            self.process_task(task)

    def _heartbeat_interval(self, response: dict[str, object]) -> float:
        value = response.get("next_heartbeat_seconds")
        if (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
            and 5 <= value <= 3600
        ):
            return float(value)
        if value is not None:
            LOG.warning(
                "Ignoring an invalid heartbeat interval from the ASHBORNE API",
                extra={
                    "event": "invalid_heartbeat_interval",
                    "agent_id": self.config.agent_id,
                },
            )
        return self.config.heartbeat_interval

    def flush_outbox(self) -> None:
        for result in self.outbox.items:
            self.client.submit_result(result)
            self.outbox.acknowledge(result.task_id)
            LOG.info(
                "Task result submitted",
                extra={"event": "task_result_submitted", "task_id": result.task_id},
            )

    def process_task(self, task: PendingTask) -> None:
        if task.agent_id != self.config.agent_id:
            raise ProtocolError("refusing a task assigned to another agent")
        self.client.start_task(task.id)
        LOG.info(
            "Task started",
            extra={"event": "task_started", "task_id": task.id, "task_type": task.task_type},
        )
        try:
            output = execute_task(task.task_type, task.parameters)
            result = TaskResult(task.id, "SUCCESS", result=output)
        except (TaskValidationError, TaskExecutionError) as exc:
            result = TaskResult(task.id, "FAILED", error_message=str(exc))
        self.outbox.enqueue(result)
        self.client.submit_result(result)
        self.outbox.acknowledge(task.id)
        LOG.info(
            "Task completed",
            extra={
                "event": "task_completed",
                "task_id": task.id,
                "task_type": task.task_type,
                "status": result.status,
            },
        )
