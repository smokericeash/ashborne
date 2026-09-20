from __future__ import annotations

import contextvars
import json
import logging
import re
from datetime import UTC, datetime

request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

_SENSITIVE_VALUE = re.compile(
    r"(?i)\b(password|refresh_token|access_token|authorization|credential|secret|token)\b"
    r"(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^,;\s]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[^,;\s\"']+")
_OPAQUE_TOKEN = re.compile(r"\b(?:kac|ket)_[A-Za-z0-9._~-]+")
_JWT_TOKEN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_URL_PASSWORD = re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^:/@\s]+:)[^@/\s]+(@)")


def redact_log_text(value: str) -> str:
    """Remove common ASHBORNE secret forms before a record reaches a handler."""
    value = _BEARER_TOKEN.sub("Bearer [redacted]", value)
    value = _SENSITIVE_VALUE.sub(lambda match: f"{match.group(1)}{match.group(2)}[redacted]", value)
    value = _OPAQUE_TOKEN.sub("[redacted]", value)
    value = _JWT_TOKEN.sub("[redacted]", value)
    return _URL_PASSWORD.sub(r"\1[redacted]\2", value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "component": record.name,
            "request_id": request_id_context.get(),
            "message": redact_log_text(record.getMessage()),
        }
        for key in ("user_id", "agent_id", "event", "exception_type"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = redact_log_text(self.formatException(record.exc_info))
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
