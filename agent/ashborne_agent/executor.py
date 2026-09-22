"""Strict task validation and dispatch to dedicated lab-action handlers."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ashborne_agent import inventory
from ashborne_agent.models import MAX_RESULT_BYTES


class TaskValidationError(ValueError):
    """A task type or its typed parameters are not allowed."""


class TaskExecutionError(RuntimeError):
    """An allowlisted lab action failed safely."""


Handler = Callable[[dict[str, Any]], dict[str, Any]]
Validator = Callable[[object], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class TaskSpec:
    handler: Handler
    validator: Validator


TASK_SPECS: dict[str, TaskSpec] = {
    "KALI_OPERATION": TaskSpec(
        lambda _value: _controller_only(),
        lambda value: _kali_parameters(value),
    ),
    "QUICK_RECON": TaskSpec(inventory.get_quick_recon, lambda value: _no_parameters(value)),
    "SYSTEM_INFO": TaskSpec(inventory.get_system_info, lambda value: _no_parameters(value)),
    "HOSTNAME": TaskSpec(inventory.get_hostname, lambda value: _no_parameters(value)),
    "CURRENT_USER": TaskSpec(inventory.get_current_user, lambda value: _no_parameters(value)),
    "SECURITY_CONTEXT": TaskSpec(
        inventory.get_security_context, lambda value: _no_parameters(value)
    ),
    "LINUX_KERNEL_INFO": TaskSpec(
        inventory.get_linux_kernel_info, lambda value: _no_parameters(value)
    ),
    "LINUX_IDENTITY": TaskSpec(inventory.get_linux_identity, lambda value: _no_parameters(value)),
    "GROUP_MEMBERSHIP": TaskSpec(
        inventory.get_group_membership, lambda value: _no_parameters(value)
    ),
    "LINUX_CAPABILITIES": TaskSpec(
        inventory.get_linux_capabilities, lambda value: _no_parameters(value)
    ),
    "LINUX_MOUNTS": TaskSpec(inventory.get_linux_mounts, lambda value: _no_parameters(value)),
    "SAFE_ENVIRONMENT_OVERVIEW": TaskSpec(
        inventory.get_safe_environment_overview, lambda value: _no_parameters(value)
    ),
    "SERVICE_OVERVIEW": TaskSpec(
        inventory.get_service_overview, lambda value: _no_parameters(value)
    ),
    "SCHEDULED_ACTIVITY_OVERVIEW": TaskSpec(
        inventory.get_scheduled_activity_overview, lambda value: _no_parameters(value)
    ),
    "PRIVILEGE_ENUMERATION": TaskSpec(
        inventory.get_privilege_enumeration, lambda value: _no_parameters(value)
    ),
    "NETWORK_OVERVIEW": TaskSpec(
        inventory.get_network_overview, lambda value: _no_parameters(value)
    ),
    "HOST_RECON": TaskSpec(inventory.get_host_recon, lambda value: _no_parameters(value)),
    "CPU_INFO": TaskSpec(inventory.get_cpu_info, lambda value: _no_parameters(value)),
    "MEMORY_USAGE": TaskSpec(inventory.get_memory_usage, lambda value: _no_parameters(value)),
    "DISK_USAGE": TaskSpec(inventory.get_disk_usage, lambda value: _disk_parameters(value)),
    "FILE_SYSTEM_OVERVIEW": TaskSpec(
        inventory.get_file_system_overview, lambda value: _no_parameters(value)
    ),
    "NETWORK_INTERFACES": TaskSpec(
        inventory.get_network_interfaces, lambda value: _no_parameters(value)
    ),
    "NETWORK_CONNECTIONS": TaskSpec(
        inventory.get_network_connections,
        lambda value: _limit_parameters(value, default=200, maximum=inventory.MAX_CONNECTIONS),
    ),
    "ROUTE_TABLE": TaskSpec(inventory.get_route_table, lambda value: _no_parameters(value)),
    "UPTIME": TaskSpec(inventory.get_uptime, lambda value: _no_parameters(value)),
    "PROCESS_INVENTORY": TaskSpec(
        inventory.get_process_inventory,
        lambda value: _limit_parameters(value, default=200, maximum=inventory.MAX_PROCESSES),
    ),
    "INSTALLED_SOFTWARE": TaskSpec(
        inventory.get_installed_software,
        lambda value: _limit_parameters(value, default=300, maximum=inventory.MAX_SOFTWARE),
    ),
    "LISTENING_PORTS": TaskSpec(
        inventory.get_listening_ports,
        lambda value: _limit_parameters(value, default=300, maximum=inventory.MAX_PORTS),
    ),
    "AGENT_HEALTH": TaskSpec(inventory.get_agent_health, lambda value: _no_parameters(value)),
    "PING": TaskSpec(inventory.ping, lambda value: _ping_parameters(value)),
}

# Public immutable-looking view used by UI/schema tests. Dispatch uses TASK_SPECS.
TASK_HANDLERS: dict[str, Handler] = {name: spec.handler for name, spec in TASK_SPECS.items()}
ALLOWED_TASK_TYPES = frozenset(TASK_SPECS)


def execute_task(task_type: object, parameters: object) -> dict[str, Any]:
    if not isinstance(task_type, str) or task_type not in TASK_SPECS:
        raise TaskValidationError("task type is not allowlisted")
    spec = TASK_SPECS[task_type]
    validated = spec.validator(parameters)
    try:
        data = spec.handler(validated)
    except TaskValidationError:
        raise
    except Exception as exc:
        # The exception text may contain local paths or other unnecessary details.
        raise TaskExecutionError(f"{task_type} lab action failed ({type(exc).__name__})") from exc
    result = {
        "task_type": task_type,
        "collected_at": datetime.now(UTC).isoformat(),
        "data": data,
    }
    try:
        encoded = json.dumps(
            result,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TaskExecutionError("lab action returned a non-serializable result") from exc
    if len(encoded) > MAX_RESULT_BYTES:
        raise TaskExecutionError("lab-action result exceeded the local size limit")
    return result


def validate_task(task_type: object, parameters: object) -> dict[str, Any]:
    if not isinstance(task_type, str) or task_type not in TASK_SPECS:
        raise TaskValidationError("task type is not allowlisted")
    return TASK_SPECS[task_type].validator(parameters)


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TaskValidationError("parameters must be a JSON object")
    if any(not isinstance(key, str) for key in value):
        raise TaskValidationError("parameter names must be strings")
    return value


def _reject_unknown(value: dict[str, Any], allowed: set[str]) -> None:
    unknown = value.keys() - allowed
    if unknown:
        raise TaskValidationError(f"unsupported parameter: {sorted(unknown)[0]}")


def _no_parameters(value: object) -> dict[str, Any]:
    parameters = _object(value)
    _reject_unknown(parameters, set())
    return {}


def _limit_parameters(value: object, *, default: int, maximum: int) -> dict[str, Any]:
    parameters = _object(value)
    _reject_unknown(parameters, {"limit"})
    limit = parameters.get("limit", default)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= maximum:
        raise TaskValidationError(f"limit must be an integer between 1 and {maximum}")
    return {"limit": limit}


def _disk_parameters(value: object) -> dict[str, Any]:
    parameters = _object(value)
    _reject_unknown(parameters, {"all_partitions"})
    include_all = parameters.get("all_partitions", False)
    if not isinstance(include_all, bool):
        raise TaskValidationError("all_partitions must be a boolean")
    return {"all_partitions": include_all}


def _ping_parameters(value: object) -> dict[str, Any]:
    parameters = _object(value)
    _reject_unknown(parameters, {"message"})
    message = parameters.get("message")
    if message is not None and (not isinstance(message, str) or len(message) > 256):
        raise TaskValidationError("message must be a string of at most 256 characters")
    return {"message": message}


def _kali_parameters(value: object) -> dict[str, Any]:
    parameters = _object(value)
    _reject_unknown(parameters, {"command", "execution_mode", "timeout_seconds"})
    command = parameters.get("command")
    if (
        not isinstance(command, str)
        or not command.strip()
        or len(command) > 4096
        or "\x00" in command
    ):
        raise TaskValidationError("command must be 1-4096 characters without NUL")
    mode = parameters.get("execution_mode", "ssh")
    if mode not in {"ssh", "local"}:
        raise TaskValidationError("execution_mode must be ssh or local")
    timeout = parameters.get("timeout_seconds", 120)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 900:
        raise TaskValidationError("timeout_seconds must be an integer between 1 and 900")
    return {"command": command, "execution_mode": mode, "timeout_seconds": timeout}


def _controller_only() -> dict[str, Any]:
    raise TaskValidationError("KALI_OPERATION requires an enrolled Kali controller")
