#!/usr/bin/env python3
"""Regression checks for ASHBORNE's Compose network and host-port contract."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"


def indented_block(content: str, section: str, name: str, indent: int) -> str:
    section_match = re.search(rf"(?m)^{re.escape(section)}:\s*$", content)
    if not section_match:
        raise AssertionError(f"missing {section} section")
    tail = content[section_match.end() :]
    prefix = " " * indent
    match = re.search(
        rf"(?ms)^{re.escape(prefix + name)}:\s*$\n(.*?)(?=^{re.escape(prefix)}\S|\Z)",
        tail,
    )
    if not match:
        raise AssertionError(f"missing {section}.{name}")
    return match.group(1)


def main() -> int:
    content = COMPOSE.read_text(encoding="utf-8")
    data_network = indented_block(content, "networks", "ashborne-data", 2)
    agent_network = indented_block(content, "networks", "ashborne-agent", 2)
    proxy_network = indented_block(content, "networks", "ashborne-proxy", 2)
    backend = indented_block(content, "services", "ashborne-backend", 2)
    frontend = indented_block(content, "services", "ashborne-frontend", 2)

    assert re.search(r"(?m)^    internal:\s*true\s*$", data_network)
    assert re.search(r"(?m)^    internal:\s*true\s*$", agent_network)
    assert not re.search(r"(?m)^    internal:\s*true\s*$", proxy_network)
    assert '"127.0.0.1:${ASHBORNE_API_PORT:-8000}:8000"' in backend
    assert '"127.0.0.1:${ASHBORNE_UI_PORT:-3000}:8080"' in frontend
    assert "ashborne-proxy:" in frontend
    assert "ashborne-proxy" in backend
    print("ASHBORNE Compose isolation and host-port contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
