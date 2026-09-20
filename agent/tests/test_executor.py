from __future__ import annotations

import inspect
from dataclasses import replace

import pytest

from ashborne_agent import executor
from ashborne_agent.executor import (
    ALLOWED_TASK_TYPES,
    TASK_HANDLERS,
    TaskExecutionError,
    TaskValidationError,
    execute_task,
    validate_task,
)

EXPECTED_ALLOWLIST = {
    "QUICK_RECON",
    "SYSTEM_INFO",
    "HOSTNAME",
    "CURRENT_USER",
    "SECURITY_CONTEXT",
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
    "CPU_INFO",
    "MEMORY_USAGE",
    "DISK_USAGE",
    "FILE_SYSTEM_OVERVIEW",
    "NETWORK_INTERFACES",
    "NETWORK_CONNECTIONS",
    "ROUTE_TABLE",
    "UPTIME",
    "PROCESS_INVENTORY",
    "INSTALLED_SOFTWARE",
    "LISTENING_PORTS",
    "AGENT_HEALTH",
    "PING",
}


def test_allowlist_is_exact() -> None:
    assert ALLOWED_TASK_TYPES == EXPECTED_ALLOWLIST
    assert set(TASK_HANDLERS) == EXPECTED_ALLOWLIST


@pytest.mark.parametrize("task_type", ["SHELL", "COMMAND", "POWERSHELL", "", None, 1])
def test_unknown_or_non_string_task_is_rejected(task_type: object) -> None:
    with pytest.raises(TaskValidationError, match="allowlisted"):
        execute_task(task_type, {})


@pytest.mark.parametrize(
    ("task_type", "parameters"),
    [
        ("HOSTNAME", {"command": "whoami"}),
        ("PROCESS_INVENTORY", {"limit": True}),
        ("PROCESS_INVENTORY", {"limit": 501}),
        ("NETWORK_CONNECTIONS", {"limit": 501}),
        ("DISK_USAGE", {"all_partitions": "yes"}),
        ("PING", {"message": "x" * 257}),
        ("PING", []),
    ],
)
def test_invalid_parameters_are_rejected(task_type: str, parameters: object) -> None:
    with pytest.raises(TaskValidationError):
        validate_task(task_type, parameters)


def test_parameters_are_normalized() -> None:
    assert validate_task("PROCESS_INVENTORY", {}) == {"limit": 200}
    assert validate_task("NETWORK_CONNECTIONS", {}) == {"limit": 200}
    assert validate_task("DISK_USAGE", {}) == {"all_partitions": False}
    assert validate_task("PING", {}) == {"message": None}


@pytest.mark.parametrize(
    ("task_type", "parameters"),
    [
        ("QUICK_RECON", {}),
        ("SYSTEM_INFO", {}),
        ("HOSTNAME", {}),
        ("CURRENT_USER", {}),
        ("SECURITY_CONTEXT", {}),
        ("LINUX_KERNEL_INFO", {}),
        ("LINUX_IDENTITY", {}),
        ("GROUP_MEMBERSHIP", {}),
        ("LINUX_CAPABILITIES", {}),
        ("LINUX_MOUNTS", {}),
        ("SAFE_ENVIRONMENT_OVERVIEW", {}),
        ("SERVICE_OVERVIEW", {}),
        ("SCHEDULED_ACTIVITY_OVERVIEW", {}),
        ("PRIVILEGE_ENUMERATION", {}),
        ("NETWORK_OVERVIEW", {}),
        ("HOST_RECON", {}),
        ("CPU_INFO", {}),
        ("MEMORY_USAGE", {}),
        ("DISK_USAGE", {}),
        ("FILE_SYSTEM_OVERVIEW", {}),
        ("NETWORK_INTERFACES", {}),
        ("NETWORK_CONNECTIONS", {"limit": 2}),
        ("ROUTE_TABLE", {}),
        ("UPTIME", {}),
        ("PROCESS_INVENTORY", {"limit": 2}),
        ("INSTALLED_SOFTWARE", {"limit": 2}),
        ("LISTENING_PORTS", {"limit": 2}),
        ("AGENT_HEALTH", {}),
        ("PING", {"message": "hello"}),
    ],
)
def test_every_allowlisted_handler_returns_structured_data(
    task_type: str, parameters: dict[str, object]
) -> None:
    result = execute_task(task_type, parameters)
    assert result["task_type"] == task_type
    assert isinstance(result["collected_at"], str)
    assert isinstance(result["data"], dict)


def test_quick_recon_is_local_and_passive() -> None:
    data = execute_task("QUICK_RECON", {})["data"]
    assert data["scope"] == "local_host_only"
    assert data["active_network_probing"] is False
    assert data["file_system"]["contents_collected"] is False


def test_handler_failures_are_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_parameters: dict[str, object]) -> dict[str, object]:
        raise OSError("sensitive/local/path")

    monkeypatch.setitem(
        executor.TASK_SPECS,
        "PING",
        replace(executor.TASK_SPECS["PING"], handler=fail),  # type: ignore[arg-type]
    )
    with pytest.raises(TaskExecutionError) as caught:
        execute_task("PING", {})
    assert "sensitive/local/path" not in str(caught.value)


def test_oversized_handler_result_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def huge(_parameters: dict[str, object]) -> dict[str, object]:
        return {"value": "x" * executor.MAX_RESULT_BYTES}

    monkeypatch.setitem(
        executor.TASK_SPECS,
        "PING",
        replace(executor.TASK_SPECS["PING"], handler=huge),  # type: ignore[arg-type]
    )
    with pytest.raises(TaskExecutionError, match="size limit"):
        execute_task("PING", {})


def test_execution_modules_have_no_shell_or_subprocess_surface() -> None:
    import ashborne_agent.inventory as inventory

    source = inspect.getsource(inventory) + inspect.getsource(executor)
    assert "shell=True" not in source
    assert "import subprocess" not in source
    assert "from subprocess" not in source
    assert "os.system" not in source
