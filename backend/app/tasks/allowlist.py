from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models import TaskType


class NoParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiskUsageParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    all_partitions: bool = False


class ProcessInventoryParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=200, ge=1, le=500)


class InstalledSoftwareParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=300, ge=1, le=500)


class ListeningPortsParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=300, ge=1, le=500)


class PingParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str | None = Field(default=None, max_length=256)


ALLOWED_TASKS: dict[TaskType, type[BaseModel]] = {task_type: NoParameters for task_type in TaskType}
PARAMETERIZED_TASKS: dict[TaskType, type[BaseModel]] = {
    TaskType.DISK_USAGE: DiskUsageParameters,
    TaskType.PROCESS_INVENTORY: ProcessInventoryParameters,
    TaskType.INSTALLED_SOFTWARE: InstalledSoftwareParameters,
    TaskType.LISTENING_PORTS: ListeningPortsParameters,
    TaskType.PING: PingParameters,
}
ALLOWED_TASKS.update(PARAMETERIZED_TASKS)


def validate_task_parameters(task_type: TaskType, parameters: dict[str, Any] | None) -> dict[str, Any]:
    schema = ALLOWED_TASKS.get(task_type)
    if schema is None:
        raise ValueError("task type is not allowlisted")
    try:
        return schema.model_validate(parameters or {}).model_dump()
    except ValidationError as exc:
        raise ValueError("parameters are not valid for this allowlisted task") from exc
