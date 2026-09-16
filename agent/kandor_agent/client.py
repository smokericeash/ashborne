"""TLS-verifying HTTP client for the KANDOR agent protocol."""

from __future__ import annotations

import logging
import random
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from kandor_agent import __version__
from kandor_agent.config import AgentConfig
from kandor_agent.models import PendingTask, ProtocolError, TaskResult

LOG = logging.getLogger("kandor_agent.client")
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TASKS_PER_RESPONSE = 100


class AgentAPIError(RuntimeError):
    """A sanitized KANDOR API or transport error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class AuthenticationError(AgentAPIError):
    """The stored agent credential was rejected."""


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 4
    base_delay: float = 0.5
    maximum_delay: float = 15.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int):
            raise ValueError("retry attempts must be an integer")
        if not 1 <= self.attempts <= 10:
            raise ValueError("retry attempts must be between 1 and 10")
        _validate_retry_number("base delay", self.base_delay, minimum=0, maximum=60)
        _validate_retry_number(
            "maximum delay", self.maximum_delay, minimum=self.base_delay, maximum=300
        )
        _validate_retry_number("jitter ratio", self.jitter_ratio, minimum=0, maximum=1)

    def delay(self, retry_number: int, random_value: float) -> float:
        base = min(self.maximum_delay, self.base_delay * (2 ** max(0, retry_number - 1)))
        jitter = base * self.jitter_ratio * max(0.0, min(random_value, 1.0))
        return float(base + jitter)


class KandorClient:
    def __init__(
        self,
        config: AgentConfig,
        *,
        retry_policy: RetryPolicy | None = None,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        random_source: Callable[[], float] = random.random,
    ) -> None:
        self.config = config
        self.retry_policy = retry_policy or RetryPolicy()
        self._sleep = sleeper
        self._random = random_source
        verify: ssl.SSLContext | bool = True
        if config.ca_bundle:
            verify = ssl.create_default_context(cafile=config.ca_bundle)
        self._client = httpx.Client(
            base_url=f"{config.server_url}/",
            timeout=httpx.Timeout(config.request_timeout),
            verify=verify,
            transport=transport,
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": f"kandor-agent/{__version__}",
            },
        )

    def __enter__(self) -> KandorClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def enroll(self, token: str, identity: dict[str, Any]) -> str:
        _validate_secret(token, "enrollment token")
        payload = {"token": token, **identity}
        response = self._request(
            "POST", "/api/v1/enrollment", json_body=payload, authenticated=False
        )
        return _extract_credential(response)

    def enroll_demo(self, bootstrap_secret: str, identity: dict[str, Any]) -> str:
        _validate_secret(bootstrap_secret, "demo bootstrap secret")
        response = self._request(
            "POST",
            "/api/v1/enrollment/demo",
            json_body=identity,
            authenticated=False,
            headers={"X-Kandor-Demo-Secret": bootstrap_secret},
        )
        return _extract_credential(response)

    def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/api/v1/agents/{self.config.agent_id}/heartbeat",
            json_body=payload,
        )
        if not isinstance(response, dict):
            raise ProtocolError("heartbeat response must be an object")
        return response

    def pending_tasks(self) -> list[PendingTask]:
        response = self._request("GET", f"/api/v1/agents/{self.config.agent_id}/tasks")
        if not isinstance(response, dict) or not isinstance(response.get("items"), list):
            raise ProtocolError("pending-task response must contain an items array")
        raw_items = response["items"]
        if len(raw_items) > MAX_TASKS_PER_RESPONSE:
            raise ProtocolError("pending-task response exceeds the local task limit")
        tasks = [PendingTask.from_api(value) for value in raw_items]
        if any(task.agent_id != self.config.agent_id for task in tasks):
            raise ProtocolError("server returned a task assigned to another agent")
        return tasks

    def start_task(self, task_id: str) -> dict[str, Any]:
        response = self._request("POST", f"/api/v1/tasks/{task_id}/start", json_body={})
        if not isinstance(response, dict):
            raise ProtocolError("task-start response must be an object")
        return response

    def submit_result(self, result: TaskResult) -> dict[str, Any]:
        response = self._request(
            "POST", f"/api/v1/tasks/{result.task_id}/result", json_body=result.to_api()
        )
        if not isinstance(response, dict):
            raise ProtocolError("task-result response must be an object")
        return response

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        authenticated: bool = True,
        headers: dict[str, str] | None = None,
    ) -> Any:
        request_headers = dict(headers or {})
        if authenticated:
            credential = self.config.credential
            if not credential:
                raise AuthenticationError("agent is not enrolled", status_code=None)
            request_headers["Authorization"] = f"Bearer {credential}"

        last_transport_error: httpx.RequestError | None = None
        for attempt in range(1, self.retry_policy.attempts + 1):
            try:
                response = self._client.request(
                    method, path, json=json_body, headers=request_headers
                )
            except httpx.RequestError as exc:
                last_transport_error = exc
                if attempt >= self.retry_policy.attempts:
                    break
                delay = self.retry_policy.delay(attempt, self._random())
                LOG.warning(
                    "KANDOR API transport failure; retrying",
                    extra={"event": "api_retry", "attempt": attempt, "delay_seconds": delay},
                )
                self._sleep(delay)
                continue

            if response.status_code in {401, 403} and authenticated:
                raise AuthenticationError(
                    "agent credential was rejected", status_code=response.status_code
                )
            if response.is_success:
                return _decode_response(response)

            retryable = response.status_code in {408, 425, 429, 500, 502, 503, 504}
            if retryable and attempt < self.retry_policy.attempts:
                delay = _retry_after(response) or self.retry_policy.delay(attempt, self._random())
                LOG.warning(
                    "KANDOR API returned a retryable status",
                    extra={
                        "event": "api_retry",
                        "attempt": attempt,
                        "status_code": response.status_code,
                        "delay_seconds": delay,
                    },
                )
                self._sleep(delay)
                continue
            raise AgentAPIError(
                f"KANDOR API request failed with HTTP {response.status_code}",
                status_code=response.status_code,
                retryable=retryable,
            )

        raise AgentAPIError(
            "could not connect to the KANDOR API",
            retryable=True,
        ) from last_transport_error


def enrollment_identity(config: AgentConfig) -> dict[str, Any]:
    uname = __import__("platform").uname()
    from kandor_agent.inventory import primary_ip_address

    try:
        username = __import__("getpass").getuser()
    except (OSError, KeyError):
        username = "unknown"
    return {
        "agent_id": config.agent_id,
        "name": config.name[:120],
        "hostname": __import__("socket").gethostname()[:255],
        "username": username[:255],
        "operating_system": uname.system[:120],
        "os_version": __import__("platform").platform(aliased=True)[:255],
        "architecture": (uname.machine or "unknown")[:64],
        "agent_version": __version__,
        "ip_address": primary_ip_address(),
    }


def heartbeat_payload() -> dict[str, Any]:
    import os
    import socket

    import psutil

    from kandor_agent.inventory import primary_ip_address

    memory = psutil.virtual_memory()
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "agent_version": __version__,
        "uptime_seconds": max(0, int(time.time() - psutil.boot_time())),
        "hostname": socket.gethostname()[:255],
        "ip_address": primary_ip_address(),
        "health": {
            "process_id": os.getpid(),
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": memory.percent,
        },
    }


def _decode_response(response: httpx.Response) -> Any:
    content = response.content
    if len(content) > MAX_RESPONSE_BYTES:
        raise ProtocolError("KANDOR API response exceeds the local size limit")
    if not content:
        return {}
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type.casefold():
        raise ProtocolError("KANDOR API returned a non-JSON response")
    try:
        return response.json()
    except ValueError as exc:
        raise ProtocolError("KANDOR API returned invalid JSON") from exc


def _extract_credential(response: object) -> str:
    if not isinstance(response, dict):
        raise ProtocolError("enrollment response must be an object")
    credential = response.get("credential")
    if not isinstance(credential, str) or not 16 <= len(credential) <= 4096:
        raise ProtocolError("enrollment response did not contain a valid credential")
    try:
        _validate_secret(credential, "agent credential")
    except ValueError as exc:
        raise ProtocolError("enrollment response did not contain a valid credential") from exc
    return credential


def _validate_secret(value: object, label: str) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= 4096:
        raise ValueError(f"{label} is invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{label} contains control characters")


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        return None
    if 0 < seconds <= 60:
        return seconds
    return None


def _validate_retry_number(label: str, value: object, *, minimum: float, maximum: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"retry {label} must be a number")
    if not minimum <= value <= maximum:
        raise ValueError(f"retry {label} must be between {minimum:g} and {maximum:g}")
