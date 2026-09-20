from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from typing import Any, ClassVar

import pytest

from ashborne_agent import main as cli
from ashborne_agent.config import AgentConfig


class EnrollmentClient:
    calls: ClassVar[list[tuple[str, Any]]] = []

    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    def __enter__(self) -> EnrollmentClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def enroll(self, token: str, identity: dict[str, Any]) -> str:
        self.calls.append((token, identity))
        return "issued-credential-value-123456"


def test_cli_enrollment_persists_uuid_and_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    EnrollmentClient.calls.clear()
    monkeypatch.setattr(cli, "AshborneClient", EnrollmentClient)
    path = tmp_path / "agent.json"

    status = cli.main(
        [
            "enroll",
            "--config",
            str(path),
            "--server",
            "https://ashborne.example",
            "--token",
            "one-time-token",
            "--name",
            "test-node",
        ]
    )

    assert status == 0
    config = AgentConfig.load(path)
    assert config.credential == "issued-credential-value-123456"
    assert EnrollmentClient.calls[0][1]["agent_id"] == config.agent_id
    assert EnrollmentClient.calls[0][1]["name"] == "test-node"


def test_cli_refuses_to_overwrite_enrollment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "AshborneClient", EnrollmentClient)
    path = tmp_path / "agent.json"
    AgentConfig.new("https://ashborne.example", name="node").save(path)
    config = AgentConfig.load(path)
    config.credential = "existing-credential-value"
    config.save(path)

    status = cli.main(["enroll", "--config", str(path), "--token", "a-different-token"])

    assert status == 2
    assert AgentConfig.load(path).credential == "existing-credential-value"


def test_status_output_never_contains_credential(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "agent.json"
    config = AgentConfig.new("https://ashborne.example", name="node")
    config.credential = "highly-secret-agent-credential"
    config.save(path)

    assert cli.main(["status", "--config", str(path), "--json"]) == 0
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert parsed["enrolled"] is True
    assert "highly-secret" not in output
    assert "credential" not in parsed


def test_status_returns_nonzero_when_not_enrolled(tmp_path: Path) -> None:
    path = tmp_path / "agent.json"
    AgentConfig.new("https://ashborne.example", name="node").save(path)
    assert cli.main(["status", "--config", str(path), "--json"]) == 1


def test_run_config_can_be_created_for_explicit_local_lab(tmp_path: Path) -> None:
    arguments = Namespace(
        config=str(tmp_path / "agent.json"),
        server="http://ashborne-backend:8000",
        name="demo",
        ca_bundle=None,
        allow_insecure_http=True,
        heartbeat_interval=10,
        poll_interval=2,
    )
    config = cli._load_run_config(arguments, Path(arguments.config))
    assert config.allow_insecure_http is True
    assert config.heartbeat_interval == 10
    assert config.poll_interval == 2
