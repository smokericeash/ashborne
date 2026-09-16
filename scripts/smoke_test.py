#!/usr/bin/env python3
"""Exercise the running KANDOR stack through its public HTTP contracts."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass
class Response:
    status: int
    body: Any
    headers: Any


class Client:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        token: str | None = None,
        expected: int | set[int] = 200,
    ) -> Response:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Accept": "application/json", "X-Request-ID": f"smoke-{uuid.uuid4()}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=15) as result:
                raw = result.read()
                response = Response(result.status, json.loads(raw) if raw else None, result.headers)
        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                error_body = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                error_body = raw.decode("utf-8", errors="replace")[:500]
            response = Response(error.code, error_body, error.headers)
        allowed = {expected} if isinstance(expected, int) else expected
        if response.status not in allowed:
            safe_body = response.body
            if isinstance(safe_body, dict):
                safe_body = {key: value for key, value in safe_body.items() if "token" not in key and "credential" not in key}
            raise AssertionError(f"{method} {path}: expected {sorted(allowed)}, got {response.status}: {safe_body}")
        return response


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    dotenv = load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Validate a running KANDOR stack")
    parser.add_argument("--url", default=os.getenv("KANDOR_SMOKE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--admin-email", default="admin@example.local")
    parser.add_argument("--admin-password", default=os.getenv("KANDOR_ADMIN_PASSWORD") or dotenv.get("KANDOR_ADMIN_PASSWORD"))
    parser.add_argument("--viewer-email", default="viewer@example.local")
    parser.add_argument("--viewer-password", default=os.getenv("KANDOR_VIEWER_PASSWORD") or dotenv.get("KANDOR_VIEWER_PASSWORD"))
    args = parser.parse_args()
    if not args.admin_password or not args.viewer_password:
        parser.error("admin and viewer passwords must be provided by environment or .env")

    api = Client(args.url)
    steps: list[str] = []

    live = api.request("GET", "/health/live")
    ready = api.request("GET", "/health/ready")
    require(live.body.get("service") == "kandor-backend", "unexpected liveness identity")
    require(ready.body.get("status") == "ready", "database is not ready")
    require(live.headers.get("X-Content-Type-Options") == "nosniff", "security headers are missing")
    steps.append("health and security headers")

    login = api.request(
        "POST",
        "/api/v1/auth/login",
        body={"email": args.admin_email, "password": args.admin_password},
    ).body
    admin_access = login["access_token"]
    original_refresh = login["refresh_token"]
    require(login["user"]["role"] == "ADMINISTRATOR", "seed administrator has the wrong role")
    api.request("POST", "/api/v1/auth/login", body={"email": args.admin_email, "password": "definitely-wrong"}, expected=401)
    steps.append("successful and rejected login")

    metrics = api.request("GET", "/api/v1/dashboard/metrics", token=admin_access).body
    require("total_agents" in metrics and "task_success_rate" in metrics, "dashboard metrics are incomplete")
    steps.append("dashboard metrics")

    issued = api.request(
        "POST",
        "/api/v1/enrollment/tokens",
        token=admin_access,
        body={"expires_in_seconds": 300, "description": "automated smoke validation"},
        expected=201,
    ).body
    enrollment_token = issued["token"]
    agent_id = str(uuid.uuid4())
    identity = {
        "agent_id": agent_id,
        "name": f"smoke-{agent_id[:8]}",
        "hostname": "kandor-smoke.local",
        "username": "smoke-user",
        "operating_system": platform.system() or "Unknown",
        "os_version": platform.release()[:255],
        "architecture": (platform.machine() or "unknown")[:64],
        "agent_version": "0.1.0-smoke",
        "ip_address": "192.0.2.10",
        "tags": ["smoke", "automated"],
    }
    enrolled = api.request(
        "POST",
        "/api/v1/enrollment",
        body={"token": enrollment_token, **identity},
        expected=201,
    ).body
    agent_credential = enrolled["credential"]
    api.request("POST", "/api/v1/enrollment", body={"token": enrollment_token, **identity}, expected=401)
    steps.append("one-time agent enrollment and replay rejection")

    heartbeat = api.request(
        "POST",
        f"/api/v1/agents/{agent_id}/heartbeat",
        token=agent_credential,
        body={
            "timestamp": datetime.now(UTC).isoformat(),
            "agent_version": "0.1.0-smoke",
            "uptime_seconds": 42,
            "hostname": identity["hostname"],
            "ip_address": identity["ip_address"],
            "health": {"state": "ok"},
        },
    ).body
    require(heartbeat["status"] == "ONLINE", "heartbeat did not mark agent online")
    steps.append("authenticated heartbeat")

    unknown = api.request(
        "POST",
        "/api/v1/tasks",
        token=admin_access,
        body={"agent_id": agent_id, "task_type": "ARBITRARY_COMMAND", "parameters": {"command": "whoami"}},
        expected=422,
    )
    require(unknown.status == 422, "unknown task type was not rejected")

    created_task = api.request(
        "POST",
        "/api/v1/tasks",
        token=admin_access,
        body={"agent_id": agent_id, "task_type": "PING", "parameters": {"message": "safe-smoke"}},
        expected=201,
    ).body
    task_id = created_task["id"]
    pending = api.request("GET", f"/api/v1/agents/{agent_id}/tasks", token=agent_credential).body
    require(any(item["id"] == task_id for item in pending["items"]), "agent did not receive its queued task")
    started = api.request("POST", f"/api/v1/tasks/{task_id}/start", token=agent_credential, body={}).body
    require(started["status"] == "RUNNING", "task did not enter RUNNING")
    completed = api.request(
        "POST",
        f"/api/v1/tasks/{task_id}/result",
        token=agent_credential,
        body={
            "status": "SUCCESS",
            "result": {"task_type": "PING", "data": {"pong": True, "message": "safe-smoke"}},
        },
    ).body
    require(completed["status"] == "SUCCESS", "task result did not reach SUCCESS")
    steps.append("strict allowlist and full task lifecycle")

    viewer_login = api.request(
        "POST",
        "/api/v1/auth/login",
        body={"email": args.viewer_email, "password": args.viewer_password},
    ).body
    viewer_access = viewer_login["access_token"]
    api.request("GET", "/api/v1/agents", token=viewer_access)
    api.request(
        "POST",
        "/api/v1/tasks",
        token=viewer_access,
        body={"agent_id": agent_id, "task_type": "PING", "parameters": {}},
        expected=403,
    )
    api.request("GET", "/api/v1/audit?event_type=TASK_COMPLETED", token=viewer_access)
    steps.append("viewer read-only RBAC")

    audit = api.request(
        "GET",
        f"/api/v1/audit?agent_id={agent_id}&event_type=TASK_COMPLETED",
        token=admin_access,
    ).body
    require(any(event["metadata"].get("task_id") == task_id for event in audit["items"]), "task audit event is missing")
    steps.append("audit trail")

    rotated = api.request(
        "POST",
        "/api/v1/auth/refresh",
        body={"refresh_token": original_refresh},
    ).body
    require(rotated.get("refresh_token") != original_refresh, "refresh token did not rotate")
    api.request("POST", "/api/v1/auth/refresh", body={"refresh_token": original_refresh}, expected=401)
    steps.append("refresh rotation and reuse detection")

    api.request("DELETE", f"/api/v1/agents/{agent_id}", token=admin_access, expected=204)
    api.request("POST", "/api/v1/auth/logout", body={"refresh_token": rotated["refresh_token"]}, expected=204)
    steps.append("agent credential revocation and logout")

    print(f"KANDOR smoke validation passed ({len(steps)} checks):")
    for step in steps:
        print(f"  - {step}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError) as error:
        print(f"KANDOR smoke validation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
