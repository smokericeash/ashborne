"""Durable agent identity and credential configuration."""

from __future__ import annotations

import json
import os
import socket
import stat
import tempfile
from contextlib import suppress
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4


class ConfigError(ValueError):
    """Configuration is missing, unsafe, or malformed."""


def default_config_path() -> Path:
    override = os.getenv("ASHBORNE_CONFIG")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "ASHBORNE" / "agent.json"
    root = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "ashborne" / "agent.json"


def validate_server_url(value: str, *, allow_insecure_http: bool = False) -> str:
    if not isinstance(value, str):
        raise ConfigError("server URL must be a string")
    if not isinstance(allow_insecure_http, bool):
        raise ConfigError("allow_insecure_http must be a boolean")
    value = value.strip().rstrip("/")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ConfigError("server URL must not contain control characters")
    try:
        parsed = urlparse(value)
        # Accessing port makes urllib validate malformed and out-of-range ports.
        _ = parsed.port
    except ValueError as exc:
        raise ConfigError("server URL is malformed") from exc
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ConfigError("server URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigError("server URL must not contain credentials, a query, or a fragment")
    if parsed.path not in {"", "/"}:
        raise ConfigError("server URL must not contain a path")
    if parsed.scheme != "https" and not allow_insecure_http:
        raise ConfigError(
            "plain HTTP is disabled; use HTTPS or explicitly allow HTTP for a local lab"
        )
    return value


@dataclass(slots=True)
class AgentConfig:
    server_url: str
    agent_id: str
    credential: str | None = None
    name: str = ""
    heartbeat_interval: float = 30.0
    poll_interval: float = 5.0
    request_timeout: float = 15.0
    ca_bundle: str | None = None
    allow_insecure_http: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.allow_insecure_http, bool):
            raise ConfigError("allow_insecure_http must be a boolean")
        self.server_url = validate_server_url(
            self.server_url, allow_insecure_http=self.allow_insecure_http
        )
        try:
            self.agent_id = str(UUID(self.agent_id))
        except (ValueError, TypeError) as exc:
            raise ConfigError("agent_id must be a valid UUID") from exc
        if self.credential is not None:
            if not isinstance(self.credential, str) or not 16 <= len(self.credential) <= 4096:
                raise ConfigError("agent credential has an invalid length")
            if any(ord(character) < 32 or ord(character) == 127 for character in self.credential):
                raise ConfigError("agent credential contains control characters")
        if not isinstance(self.name, str):
            raise ConfigError("agent name must be a string")
        if not self.name:
            self.name = socket.gethostname()[:120] or f"ashborne-{self.agent_id[:8]}"
        if len(self.name) > 120 or any(
            ord(character) < 32 or ord(character) == 127 for character in self.name
        ):
            raise ConfigError("agent name is invalid")
        self.heartbeat_interval = _bounded_number(
            "heartbeat_interval", self.heartbeat_interval, 5, 3600
        )
        self.poll_interval = _bounded_number("poll_interval", self.poll_interval, 1, 3600)
        self.request_timeout = _bounded_number("request_timeout", self.request_timeout, 1, 120)
        if self.ca_bundle is not None and not isinstance(self.ca_bundle, str):
            raise ConfigError("ca_bundle must be a path string")
        if self.ca_bundle:
            ca_path = Path(self.ca_bundle).expanduser()
            if not ca_path.is_file():
                raise ConfigError(f"CA bundle does not exist: {ca_path}")
            self.ca_bundle = str(ca_path.resolve())
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ConfigError("unsupported agent configuration schema version")

    @classmethod
    def new(
        cls,
        server_url: str,
        *,
        name: str | None = None,
        ca_bundle: str | None = None,
        allow_insecure_http: bool = False,
    ) -> AgentConfig:
        return cls(
            server_url=server_url,
            agent_id=str(uuid4()),
            name=(name or socket.gethostname())[:120],
            ca_bundle=ca_bundle,
            allow_insecure_http=allow_insecure_http,
        )

    @classmethod
    def load(cls, path: Path) -> AgentConfig:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except FileNotFoundError as exc:
            raise ConfigError(f"agent configuration not found: {path}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"could not read agent configuration: {path}") from exc
        if not isinstance(data, dict):
            raise ConfigError("agent configuration must be a JSON object")
        allowed = {field.name for field in fields(cls)}
        unknown = data.keys() - allowed
        if unknown:
            raise ConfigError(f"unknown configuration fields: {', '.join(sorted(unknown))}")
        try:
            return cls(**data)
        except TypeError as exc:
            raise ConfigError("agent configuration is incomplete") from exc

    def save(self, path: Path) -> None:
        path = path.expanduser().resolve()
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _restrict_directory(path.parent)
        serialized = json.dumps(asdict(self), sort_keys=True, indent=2) + "\n"
        temporary_name: str | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
            )
            os.chmod(temporary_name, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, path)
            temporary_name = None
            _restrict_file(path)
        finally:
            if temporary_name:
                with suppress(OSError):
                    Path(temporary_name).unlink(missing_ok=True)

    def public_status(self, path: Path) -> dict[str, Any]:
        return {
            "config_path": str(path.expanduser().resolve()),
            "server_url": self.server_url,
            "agent_id": self.agent_id,
            "name": self.name,
            "enrolled": bool(self.credential),
            "tls_verification": "custom CA" if self.ca_bundle else "system trust store",
            "transport": "HTTPS verified" if self.server_url.startswith("https://") else "lab HTTP",
            "heartbeat_interval": self.heartbeat_interval,
            "poll_interval": self.poll_interval,
        }


def _bounded_number(name: str, value: object, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a number")
    number = float(value)
    if not minimum <= number <= maximum:
        raise ConfigError(f"{name} must be between {minimum:g} and {maximum:g}")
    return number


def _restrict_directory(path: Path) -> None:
    if os.name != "nt":
        with suppress(OSError):
            os.chmod(path, stat.S_IRWXU)


def _restrict_file(path: Path) -> None:
    with suppress(OSError):
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
