"""Durable, permission-restricted task-result outbox."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from contextlib import suppress
from pathlib import Path

from kandor_agent.models import ProtocolError, TaskResult

MAX_OUTBOX_ITEMS = 100
MAX_OUTBOX_BYTES = 50 * 1024 * 1024


class OutboxError(RuntimeError):
    pass


class ResultOutbox:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self._items: list[TaskResult] = []
        self._load()

    @classmethod
    def beside_config(cls, config_path: Path) -> ResultOutbox:
        return cls(config_path.with_name(f"{config_path.stem}.outbox.json"))

    @property
    def items(self) -> tuple[TaskResult, ...]:
        return tuple(self._items)

    def enqueue(self, result: TaskResult) -> None:
        updated = [item for item in self._items if item.task_id != result.task_id]
        if len(updated) >= MAX_OUTBOX_ITEMS:
            raise OutboxError("result outbox is full")
        updated.append(result)
        self._save(updated)
        self._items = updated

    def acknowledge(self, task_id: str) -> None:
        updated = [item for item in self._items if item.task_id != task_id]
        if len(updated) == len(self._items):
            return
        self._save(updated)
        self._items = updated

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            if self.path.stat().st_size > MAX_OUTBOX_BYTES:
                raise OutboxError("result outbox exceeds the local size limit")
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise OutboxError("could not read result outbox") from exc
        if not isinstance(data, list) or len(data) > MAX_OUTBOX_ITEMS:
            raise OutboxError("result outbox is malformed")
        parsed: list[TaskResult] = []
        task_ids: set[str] = set()
        for value in data:
            if not isinstance(value, dict):
                raise OutboxError("result outbox is malformed")
            task_id = value.get("task_id")
            status = value.get("status")
            result = value.get("result")
            error_message = value.get("error_message")
            if (
                not isinstance(task_id, str)
                or status not in {"SUCCESS", "FAILED"}
                or (result is not None and not isinstance(result, dict))
                or (error_message is not None and not isinstance(error_message, str))
            ):
                raise OutboxError("result outbox is malformed")
            try:
                parsed_result = TaskResult(task_id, status, result, error_message)
            except ProtocolError as exc:
                raise OutboxError("result outbox is malformed") from exc
            if parsed_result.task_id in task_ids:
                raise OutboxError("result outbox contains duplicate task results")
            task_ids.add(parsed_result.task_id)
            parsed.append(parsed_result)
        self._items = parsed

    def _save(self, items: list[TaskResult]) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _restrict_directory(self.path.parent)
        data = [
            {
                "task_id": item.task_id,
                "status": item.status,
                "result": item.result,
                "error_message": item.error_message,
            }
            for item in items
        ]
        try:
            serialized = (
                json.dumps(
                    data,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
        except (TypeError, ValueError) as exc:
            raise OutboxError("result outbox contains non-serializable data") from exc
        if len(serialized.encode("utf-8")) > MAX_OUTBOX_BYTES:
            raise OutboxError("result outbox exceeds the local size limit")
        temporary_name: str | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
            )
            os.chmod(temporary_name, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, self.path)
            temporary_name = None
            _restrict_file(self.path)
        finally:
            if temporary_name:
                with suppress(OSError):
                    Path(temporary_name).unlink(missing_ok=True)


def _restrict_directory(path: Path) -> None:
    if os.name != "nt":
        with suppress(OSError):
            os.chmod(path, stat.S_IRWXU)


def _restrict_file(path: Path) -> None:
    with suppress(OSError):
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
