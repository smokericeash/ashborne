from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

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


class NetworkConnectionsParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=200, ge=1, le=500)


class PingParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str | None = Field(default=None, max_length=256)


class KaliOperationParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str = Field(min_length=1, max_length=4096)
    execution_mode: Literal["ssh", "local"] = "ssh"
    timeout_seconds: int = Field(default=120, ge=1, le=900)

    @field_validator("command")
    @classmethod
    def command_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("command cannot be blank")
        if "\x00" in value:
            raise ValueError("command cannot contain NUL")
        return value


NO_PARAMETER_TASKS = (
    TaskType.QUICK_RECON,
    TaskType.SYSTEM_INFO,
    TaskType.HOSTNAME,
    TaskType.CURRENT_USER,
    TaskType.SECURITY_CONTEXT,
    TaskType.CPU_INFO,
    TaskType.MEMORY_USAGE,
    TaskType.FILE_SYSTEM_OVERVIEW,
    TaskType.NETWORK_INTERFACES,
    TaskType.ROUTE_TABLE,
    TaskType.UPTIME,
    TaskType.AGENT_HEALTH,
    TaskType.LINUX_KERNEL_INFO,
    TaskType.LINUX_IDENTITY,
    TaskType.GROUP_MEMBERSHIP,
    TaskType.LINUX_CAPABILITIES,
    TaskType.LINUX_MOUNTS,
    TaskType.SAFE_ENVIRONMENT_OVERVIEW,
    TaskType.SERVICE_OVERVIEW,
    TaskType.SCHEDULED_ACTIVITY_OVERVIEW,
    TaskType.PRIVILEGE_ENUMERATION,
    TaskType.NETWORK_OVERVIEW,
    TaskType.HOST_RECON,
)
ALLOWED_TASKS: dict[TaskType, type[BaseModel]] = {task_type: NoParameters for task_type in NO_PARAMETER_TASKS}
PARAMETERIZED_TASKS: dict[TaskType, type[BaseModel]] = {
    TaskType.DISK_USAGE: DiskUsageParameters,
    TaskType.PROCESS_INVENTORY: ProcessInventoryParameters,
    TaskType.INSTALLED_SOFTWARE: InstalledSoftwareParameters,
    TaskType.LISTENING_PORTS: ListeningPortsParameters,
    TaskType.NETWORK_CONNECTIONS: NetworkConnectionsParameters,
    TaskType.PING: PingParameters,
    TaskType.KALI_OPERATION: KaliOperationParameters,
}
ALLOWED_TASKS.update(PARAMETERIZED_TASKS)

if set(ALLOWED_TASKS) != set(TaskType):
    raise RuntimeError("TaskType and the reviewed ASHBORNE allowlist are out of sync")


def validate_task_parameters(task_type: TaskType, parameters: dict[str, Any] | None) -> dict[str, Any]:
    schema = ALLOWED_TASKS.get(task_type)
    if schema is None:
        raise ValueError("task type is not allowlisted")
    try:
        return schema.model_validate(parameters or {}).model_dump()
    except ValidationError as exc:
        raise ValueError("parameters are not valid for this allowlisted task") from exc
