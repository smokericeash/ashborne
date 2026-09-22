"""Agent heartbeat, polling, execution, and durable result lifecycle."""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from ashborne_agent.client import (
    AgentAPIError,
    AshborneClient,
    AuthenticationError,
    heartbeat_payload,
)
from ashborne_agent.config import AgentConfig
from ashborne_agent.executor import TaskExecutionError, TaskValidationError, execute_task
from ashborne_agent.kali import execute_operation
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
        selected = tasks[:MAX_TASKS_PER_CYCLE]
        kali_tasks = [task for task in selected if task.task_type == "KALI_OPERATION"]
        regular_tasks = [task for task in selected if task.task_type != "KALI_OPERATION"]
        for task in regular_tasks:
            if self.stop_event.is_set():
                break
            self.process_task(task)
        if kali_tasks and not self.stop_event.is_set():
            self.process_kali_tasks(kali_tasks)

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
        if task.execution_agent_id != self.config.agent_id:
            raise ProtocolError("refusing a task assigned to another agent")
        self._start_task(task)
        result = self._execute_task(task)
        self._deliver_result(result)
        self._log_completion(task, result)

    def process_kali_tasks(self, tasks: list[PendingTask]) -> None:
        if not self.config.kali_controller:
            for task in tasks:
                self.process_task(task)
            return
        runnable: list[PendingTask] = []
        for task in tasks:
            if task.execution_agent_id != self.config.agent_id:
                raise ProtocolError("refusing a task assigned to another agent")
            self._start_task(task)
            runnable.append(task)
        first_delivery_error: AgentAPIError | None = None
        with ThreadPoolExecutor(
            max_workers=self.config.max_parallel_hosts,
            thread_name_prefix="ashborne-kali",
        ) as pool:
            futures = {pool.submit(self._execute_task, task): task for task in runnable}
            for future in as_completed(futures):
                task = futures[future]
                result = future.result()
                try:
                    self._deliver_result(result)
                except AgentAPIError as exc:
                    first_delivery_error = first_delivery_error or exc
                self._log_completion(task, result)
        if first_delivery_error:
            raise first_delivery_error

    def _start_task(self, task: PendingTask) -> None:
        self.client.start_task(task.id)
        LOG.info(
            "Task started",
            extra={"event": "task_started", "task_id": task.id, "task_type": task.task_type},
        )

    def _execute_task(self, task: PendingTask) -> TaskResult:
        try:
            if task.task_type == "KALI_OPERATION":
                if not self.config.kali_controller:
                    raise TaskValidationError("KALI_OPERATION requires controller mode")
                output = execute_operation(task.parameters, task.target)
                data = output["data"]
                if data["timed_out"]:
                    return TaskResult(
                        task.id,
                        "TIMED_OUT",
                        result=output,
                        error_message="operation exceeded its configured timeout",
                    )
                if data["result_code"] != 0:
                    return TaskResult(
                        task.id,
                        "FAILED",
                        result=output,
                        error_message=f"operation exited with code {data['result_code']}",
                    )
                return TaskResult(task.id, "SUCCESS", result=output)
            output = execute_task(task.task_type, task.parameters)
            return TaskResult(task.id, "SUCCESS", result=output)
        except (TaskValidationError, TaskExecutionError) as exc:
            return TaskResult(task.id, "FAILED", error_message=str(exc))

    def _deliver_result(self, result: TaskResult) -> None:
        self.outbox.enqueue(result)
        self.client.submit_result(result)
        self.outbox.acknowledge(result.task_id)

    def _log_completion(self, task: PendingTask, result: TaskResult) -> None:
        LOG.info(
            "Task completed",
            extra={
                "event": "task_completed",
                "task_id": task.id,
                "task_type": task.task_type,
                "status": result.status,
            },
        )
