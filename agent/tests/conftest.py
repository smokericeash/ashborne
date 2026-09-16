from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from kandor_agent.config import AgentConfig


@pytest.fixture
def agent_config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(
        server_url="https://kandor.example",
        agent_id=str(uuid4()),
        credential="c" * 32,
        name="pytest-agent",
        heartbeat_interval=30,
        poll_interval=5,
        request_timeout=5,
    )
