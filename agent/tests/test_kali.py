from __future__ import annotations

import subprocess
from typing import Any

import pytest

from ashborne_agent.kali import execute_operation, validate_parameters, validate_target

TARGET = {
    "id": "4de20682-dd48-4cb0-bc64-bbe6cdd2502f",
    "name": "lab-01",
    "hostname": "lab-01",
    "username": "student",
    "ip_address": "10.20.30.40",
}


class FakeProcess:
    def __init__(self, argv: list[str], **_kwargs: Any) -> None:
        self.argv = argv
        self.pid = 123
        self.returncode = 0

    def communicate(self, timeout: int | None = None) -> tuple[bytes, bytes]:
        assert timeout == 15
        return b"ok\n", b""


def test_ssh_operation_uses_argument_vector_and_captures_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[FakeProcess] = []

    def factory(argv: list[str], **kwargs: Any) -> FakeProcess:
        process = FakeProcess(argv, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", factory)
    result = execute_operation(
        {"command": "hostname", "execution_mode": "ssh", "timeout_seconds": 15},
        TARGET,
    )["data"]

    assert created[0].argv[-2:] == ["student@10.20.30.40", "hostname"]
    assert result["stdout"] == "ok\n"
    assert result["stderr"] == ""
    assert result["result_code"] == 0
    assert result["state"] == "SUCCESS"


def test_local_operation_uses_kali_shell_and_target_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def factory(argv: list[str], **kwargs: Any) -> FakeProcess:
        captured["argv"] = argv
        captured["environment"] = kwargs["env"]
        return FakeProcess(argv, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", factory)
    execute_operation(
        {"command": "nmap $ASHBORNE_TARGET_IP", "execution_mode": "local", "timeout_seconds": 15},
        TARGET,
    )

    assert captured["argv"] == ["/bin/bash", "-lc", "nmap $ASHBORNE_TARGET_IP"]
    assert captured["environment"]["ASHBORNE_TARGET_IP"] == "10.20.30.40"


@pytest.mark.parametrize(
    "value",
    [
        {"command": ""},
        {"command": "id", "execution_mode": "invalid"},
        {"command": "id", "timeout_seconds": 0},
        {"command": "id", "extra": True},
    ],
)
def test_operation_parameters_are_bounded(value: object) -> None:
    with pytest.raises(ValueError):
        validate_parameters(value)


def test_target_rejects_unsafe_ssh_identity() -> None:
    with pytest.raises(ValueError):
        validate_target({**TARGET, "username": "-oProxyCommand=bad"})
