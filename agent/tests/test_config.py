from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from uuid import uuid4

import pytest

from kandor_agent.config import AgentConfig, ConfigError, validate_server_url


def test_https_is_required_by_default() -> None:
    with pytest.raises(ConfigError, match="plain HTTP is disabled"):
        validate_server_url("http://kandor.local")
    assert (
        validate_server_url("http://kandor.local/", allow_insecure_http=True)
        == "http://kandor.local"
    )


@pytest.mark.parametrize(
    "url",
    [
        "kandor.local",
        "ftp://kandor.local",
        "https://user:secret@kandor.local",
        "https://kandor.local/api",
        "https://kandor.local?secret=x",
        "https://kandor.local:70000",
        "https://kandor.local\n.invalid",
    ],
)
def test_rejects_unsafe_or_ambiguous_server_urls(url: str) -> None:
    with pytest.raises(ConfigError):
        validate_server_url(url)


def test_config_round_trip_is_atomic_and_credential_is_not_public(tmp_path: Path) -> None:
    path = tmp_path / "state" / "agent.json"
    config = AgentConfig(
        "https://kandor.example",
        str(uuid4()),
        credential="secret-agent-credential-value",
        name="node-1",
    )
    config.save(path)

    loaded = AgentConfig.load(path)
    assert loaded == config
    assert loaded.public_status(path)["enrolled"] is True
    assert "credential" not in loaded.public_status(path)
    assert not list(path.parent.glob("*.tmp"))
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_config_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "agent.json"
    path.write_text(
        json.dumps(
            {
                "server_url": "https://kandor.example",
                "agent_id": str(uuid4()),
                "unexpected": "value",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unknown configuration"):
        AgentConfig.load(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("heartbeat_interval", 4),
        ("poll_interval", True),
        ("request_timeout", 121),
        ("credential", "short"),
        ("credential", "x" * 16 + "\n"),
        ("name", "x" * 121),
        ("allow_insecure_http", "true"),
        ("schema_version", 2),
    ],
)
def test_config_bounds(field: str, value: object) -> None:
    arguments: dict[str, object] = {
        "server_url": "https://kandor.example",
        "agent_id": str(uuid4()),
        "credential": "x" * 32,
        "name": "valid",
    }
    arguments[field] = value
    with pytest.raises(ConfigError):
        AgentConfig(**arguments)  # type: ignore[arg-type]
