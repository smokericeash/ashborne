"""Structured local logging without secret-bearing request data."""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import stat
import sys
from contextlib import suppress
from datetime import UTC, datetime
from io import TextIOWrapper
from pathlib import Path

_STANDARD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
_SENSITIVE_FIELD_MARKERS = ("authorization", "credential", "password", "secret", "token")


class SecureRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Create the active log with owner-only permissions after every rollover."""

    def _open(self) -> TextIOWrapper:
        stream = super()._open()
        with suppress(OSError):
            os.chmod(self.baseFilename, stat.S_IRUSR | stat.S_IWUSR)
        return stream


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "severity": record.levelname,
            "component": record.name,
            "event": getattr(record, "event", "agent_log"),
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and key != "event" and not key.startswith("_"):
                if any(marker in key.casefold() for marker in _SENSITIVE_FIELD_MARKERS):
                    continue
                payload[key] = value
        if record.exc_info:
            # Exception type is useful; full exception text can contain server-provided data.
            exception_type = record.exc_info[0]
            if exception_type is not None:
                payload["exception_type"] = exception_type.__name__
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(
    *, level: str = "INFO", log_file: Path | None = None, console: bool = True
) -> None:
    root = logging.getLogger()
    for existing_handler in root.handlers:
        existing_handler.close()
    root.handlers.clear()
    root.setLevel(level.upper())
    formatter = JsonFormatter()
    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)
    if log_file is not None:
        log_file = log_file.expanduser().resolve()
        log_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        handler = SecureRotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
