"""Small validated wire models used by the ASHBORNE agent."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

MAX_RESULT_BYTES = 512 * 1024
MAX_ERROR_MESSAGE_LENGTH = 4096


class ProtocolError(ValueError):
    """The server returned a response that does not match the agent protocol."""


@dataclass(frozen=True, slots=True)
class PendingTask:
    id: str
    agent_id: str
    task_type: str
    parameters: dict[str, Any]
    executor_agent_id: str | None = None
    target: dict[str, Any] | None = None

    @classmethod
    def from_api(cls, value: object) -> PendingTask:
        if not isinstance(value, dict):
            raise ProtocolError("task must be an object")
        task_id = value.get("id")
        agent_id = value.get("agent_id")
        task_type = value.get("task_type")
        parameters = value.get("parameters", {})
        executor_agent_id = value.get("executor_agent_id")
        target = value.get("target")
        if not isinstance(task_id, str):
            raise ProtocolError("task id must be a UUID string")
        if not isinstance(agent_id, str):
            raise ProtocolError("task agent_id must be a UUID string")
        try:
            normalized_task_id = str(UUID(task_id))
            normalized_agent_id = str(UUID(agent_id))
        except ValueError as exc:
            raise ProtocolError("task identifiers must be valid UUIDs") from exc
        if not isinstance(task_type, str) or not task_type:
            raise ProtocolError("task_type must be a non-empty string")
        if not isinstance(parameters, dict):
            raise ProtocolError("task parameters must be an object")
        normalized_executor_id: str | None = None
        if executor_agent_id is not None:
            if not isinstance(executor_agent_id, str):
                raise ProtocolError("executor_agent_id must be a UUID string")
            try:
                normalized_executor_id = str(UUID(executor_agent_id))
            except ValueError as exc:
                raise ProtocolError("executor_agent_id must be a valid UUID") from exc
        if target is not None and not isinstance(target, dict):
            raise ProtocolError("task target must be an object")
        return cls(
            normalized_task_id,
            normalized_agent_id,
            task_type,
            parameters,
            normalized_executor_id,
            target,
        )

    @property
    def execution_agent_id(self) -> str:
        return self.executor_agent_id or self.agent_id


@dataclass(frozen=True, slots=True)
class TaskResult:
    task_id: str
    status: str
    result: dict[str, Any] | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        try:
            normalized = str(UUID(self.task_id))
        except (ValueError, TypeError) as exc:
            raise ProtocolError("task result id must be a valid UUID") from exc
        object.__setattr__(self, "task_id", normalized)
        if self.status not in {"SUCCESS", "FAILED", "TIMED_OUT"}:
            raise ProtocolError("task result status is invalid")
        if self.result is not None and not isinstance(self.result, dict):
            raise ProtocolError("task result data must be an object")
        if self.error_message is not None and not isinstance(self.error_message, str):
            raise ProtocolError("task result error must be a string")
        if self.status == "SUCCESS" and self.result is None:
            raise ProtocolError("successful task results require structured data")
        if self.status == "SUCCESS" and self.error_message:
            raise ProtocolError("successful task results cannot contain an error")
        if self.status != "SUCCESS" and not self.error_message:
            raise ProtocolError("unsuccessful task results require an error")
        if self.error_message is not None and len(self.error_message) > MAX_ERROR_MESSAGE_LENGTH:
            raise ProtocolError("task result error exceeds the local length limit")
        if self.result is not None:
            try:
                encoded = json.dumps(
                    self.result,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise ProtocolError("task result data must be finite JSON") from exc
            if len(encoded) > MAX_RESULT_BYTES:
                raise ProtocolError("task result data exceeds the local size limit")

    def to_api(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": self.status}
        if self.result is not None:
            payload["result"] = self.result
        if self.error_message is not None:
            payload["error_message"] = self.error_message
        return payload
