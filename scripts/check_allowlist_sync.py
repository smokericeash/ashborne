#!/usr/bin/env python3
"""Fail when backend, agent, and UI task allowlists diverge."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "QUICK_RECON",
    "SYSTEM_INFO",
    "HOSTNAME",
    "CURRENT_USER",
    "SECURITY_CONTEXT",
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
}


def backend_values() -> set[str]:
    tree = ast.parse(
        (ROOT / "backend/app/models/entities.py").read_text(encoding="utf-8")
    )
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "TaskType":
            return {
                statement.value.value
                for statement in node.body
                if isinstance(statement, ast.Assign)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            }
    raise RuntimeError("backend TaskType enum was not found")


def agent_values() -> set[str]:
    tree = ast.parse(
        (ROOT / "agent/ashborne_agent/executor.py").read_text(encoding="utf-8")
    )
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.target.id == "TASK_SPECS" and isinstance(node.value, ast.Dict):
            return {
                key.value
                for key in node.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
    raise RuntimeError("agent TASK_SPECS mapping was not found")


def frontend_values() -> set[str]:
    source = (ROOT / "frontend/src/types/index.ts").read_text(encoding="utf-8")
    match = re.search(
        r"export\s+const\s+TASK_TYPES\s*=\s*\[(.*?)\]\s*as\s+const", source, re.DOTALL
    )
    if not match:
        raise RuntimeError("frontend TASK_TYPES tuple was not found")
    return set(re.findall(r'["\']([A-Z][A-Z0-9_]*)["\']', match.group(1)))


def main() -> int:
    sources = {
        "declared safety contract": EXPECTED,
        "backend": backend_values(),
        "agent": agent_values(),
        "frontend": frontend_values(),
    }
    if all(values == EXPECTED for values in sources.values()):
        print(f"ASHBORNE allowlist synchronized: {len(EXPECTED)} typed lab actions")
        return 0
    for name, values in sources.items():
        missing = sorted(EXPECTED - values)
        extra = sorted(values - EXPECTED)
        if missing or extra:
            print(f"{name}: missing={missing or 'none'} extra={extra or 'none'}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
