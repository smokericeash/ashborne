"""Strict task validation and dispatch to dedicated diagnostic handlers."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from kandor_agent import inventory
from kandor_agent.models import MAX_RESULT_BYTES


class TaskValidationError(ValueError):
    """A task type or its typed parameters are not allowed."""


class TaskExecutionError(RuntimeError):
    """An allowlisted diagnostic failed safely."""


Handler = Callable[[dict[str, Any]], dict[str, Any]]
Validator = Callable[[object], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class TaskSpec:
    handler: Handler
    validator: Validator


TASK_SPECS: dict[str, TaskSpec] = {
    "SYSTEM_INFO": TaskSpec(inventory.get_system_info, lambda value: _no_parameters(value)),
    "HOSTNAME": TaskSpec(inventory.get_hostname, lambda value: _no_parameters(value)),
    "CURRENT_USER": TaskSpec(inventory.get_current_user, lambda value: _no_parameters(value)),
    "CPU_INFO": TaskSpec(inventory.get_cpu_info, lambda value: _no_parameters(value)),
    "MEMORY_USAGE": TaskSpec(inventory.get_memory_usage, lambda value: _no_parameters(value)),
    "DISK_USAGE": TaskSpec(inventory.get_disk_usage, lambda value: _disk_parameters(value)),
    "NETWORK_INTERFACES": TaskSpec(
        inventory.get_network_interfaces, lambda value: _no_parameters(value)
    ),
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
        raise TaskExecutionError(f"{task_type} diagnostic failed ({type(exc).__name__})") from exc
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
        raise TaskExecutionError("diagnostic returned a non-serializable result") from exc
    if len(encoded) > MAX_RESULT_BYTES:
        raise TaskExecutionError("diagnostic result exceeded the local size limit")
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
