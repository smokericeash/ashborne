"""Bounded execution primitives for an explicitly enrolled Kali controller."""

from __future__ import annotations

import ipaddress
import os
import re
import signal
import subprocess
import time
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from ashborne_agent.executor import TaskExecutionError, TaskValidationError

MAX_STREAM_BYTES = 256 * 1024
_HOSTNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
_USERNAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def validate_parameters(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TaskValidationError("parameters must be a JSON object")
    unknown = value.keys() - {"command", "execution_mode", "timeout_seconds"}
    if unknown:
        raise TaskValidationError(f"unsupported parameter: {sorted(unknown)[0]}")
    command = value.get("command")
    if (
        not isinstance(command, str)
        or not command.strip()
        or len(command) > 4096
        or "\x00" in command
    ):
        raise TaskValidationError("command must be 1-4096 characters without NUL")
    mode = value.get("execution_mode", "ssh")
    if mode not in {"ssh", "local"}:
        raise TaskValidationError("execution_mode must be ssh or local")
    timeout = value.get("timeout_seconds", 120)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 900:
        raise TaskValidationError("timeout_seconds must be an integer between 1 and 900")
    return {"command": command, "execution_mode": mode, "timeout_seconds": timeout}


def validate_target(value: object) -> dict[str, str | None]:
    if not isinstance(value, dict):
        raise TaskValidationError("Kali operations require target metadata")
    target_id = value.get("id")
    name = value.get("name")
    hostname = value.get("hostname")
    username = value.get("username")
    ip_address = value.get("ip_address")
    if (
        not isinstance(target_id, str)
        or not target_id
        or not isinstance(name, str)
        or not name
        or not isinstance(hostname, str)
        or not hostname
        or not isinstance(username, str)
        or not username
    ):
        raise TaskValidationError("target metadata is incomplete")
    if not _USERNAME.fullmatch(username):
        raise TaskValidationError("target username is not safe for SSH")
    if ip_address is not None:
        if not isinstance(ip_address, str):
            raise TaskValidationError("target IP address must be a string")
        try:
            ip_address = str(ipaddress.ip_address(ip_address))
        except ValueError as exc:
            raise TaskValidationError("target IP address is invalid") from exc
    if ip_address is None and not _HOSTNAME.fullmatch(hostname):
        raise TaskValidationError("target hostname is invalid")
    return {
        "id": target_id,
        "name": name,
        "hostname": hostname,
        "username": username,
        "ip_address": ip_address,
    }


def execute_operation(parameters: object, target_value: object) -> dict[str, Any]:
    operation = validate_parameters(parameters)
    target = validate_target(target_value)
    address = target["ip_address"] or target["hostname"]
    assert isinstance(address, str)
    environment = os.environ.copy()
    environment.update(
        {
            "ASHBORNE_TARGET_ID": str(target["id"]),
            "ASHBORNE_TARGET_NAME": str(target["name"]),
            "ASHBORNE_TARGET_HOST": str(target["hostname"]),
            "ASHBORNE_TARGET_IP": str(target["ip_address"] or ""),
            "ASHBORNE_TARGET_USER": str(target["username"]),
        }
    )
    if operation["execution_mode"] == "ssh":
        destination = f"{target['username']}@{address}"
        argv = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={min(operation['timeout_seconds'], 30)}",
            "--",
            destination,
            operation["command"],
        ]
    else:
        argv = ["/bin/bash", "-lc", operation["command"]]

    started_at = datetime.now(UTC)
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            start_new_session=True,
        )
    except OSError as exc:
        raise TaskExecutionError("Kali controller could not start the requested operation") from exc
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=operation["timeout_seconds"])
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_group(process)
        stdout, stderr = process.communicate()
    completed_at = datetime.now(UTC)
    result_code = 124 if timed_out else int(process.returncode)
    return {
        "task_type": "KALI_OPERATION",
        "collected_at": completed_at.isoformat(),
        "data": {
            "stdout": _decode(stdout),
            "stderr": _decode(stderr),
            "result_code": result_code,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_seconds": round(time.monotonic() - started, 3),
            "state": "TIMED_OUT" if timed_out else "SUCCESS" if result_code == 0 else "FAILED",
            "timed_out": timed_out,
            "execution_mode": operation["execution_mode"],
            "target": target,
        },
    }


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    killpg = getattr(os, "killpg", None)
    try:
        if os.name == "posix" and callable(killpg):
            killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        if os.name == "posix" and callable(killpg):
            with suppress(OSError):
                killpg(process.pid, getattr(signal, "SIGKILL", 9))
        else:
            process.kill()


def _decode(value: bytes) -> str:
    clipped = value[:MAX_STREAM_BYTES]
    text = clipped.decode("utf-8", errors="replace")
    if len(value) > MAX_STREAM_BYTES:
        text += f"\n[truncated after {MAX_STREAM_BYTES} bytes]"
    return text
