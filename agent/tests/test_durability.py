from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from uuid import uuid4

import pytest

from kandor_agent.logging import JsonFormatter, SecureRotatingFileHandler
from kandor_agent.models import MAX_RESULT_BYTES, ProtocolError, TaskResult
from kandor_agent.outbox import OutboxError, ResultOutbox


def successful_result(*, value: object = True) -> TaskResult:
    return TaskResult(str(uuid4()), "SUCCESS", result={"value": value})


@pytest.mark.parametrize(
    ("status", "result", "error"),
    [
        ("SUCCESS", None, None),
        ("SUCCESS", {"ok": True}, "unexpected"),
        ("FAILED", None, None),
    ],
)
def test_task_result_enforces_backend_invariants(
    status: str, result: dict[str, object] | None, error: str | None
) -> None:
    with pytest.raises(ProtocolError):
        TaskResult(str(uuid4()), status, result=result, error_message=error)


def test_task_result_rejects_non_finite_and_oversized_json() -> None:
    with pytest.raises(ProtocolError, match="finite JSON"):
        successful_result(value=float("nan"))
    with pytest.raises(ProtocolError, match="size limit"):
        successful_result(value="x" * MAX_RESULT_BYTES)


def test_outbox_enqueue_is_transactional_on_save_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outbox = ResultOutbox(tmp_path / "outbox.json")
    original = successful_result()
    outbox.enqueue(original)

    def fail(_items: list[TaskResult]) -> None:
        raise OutboxError("disk unavailable")

    monkeypatch.setattr(outbox, "_save", fail)
    with pytest.raises(OutboxError, match="disk unavailable"):
        outbox.enqueue(successful_result())
    assert outbox.items == (original,)


def test_outbox_acknowledge_is_transactional_on_save_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outbox = ResultOutbox(tmp_path / "outbox.json")
    original = successful_result()
    outbox.enqueue(original)

    def fail(_items: list[TaskResult]) -> None:
        raise OutboxError("disk unavailable")

    monkeypatch.setattr(outbox, "_save", fail)
    with pytest.raises(OutboxError, match="disk unavailable"):
        outbox.acknowledge(original.task_id)
    assert outbox.items == (original,)


def test_outbox_rejects_duplicate_or_protocol_invalid_records(tmp_path: Path) -> None:
    task_id = str(uuid4())
    path = tmp_path / "outbox.json"
    record = {
        "task_id": task_id,
        "status": "SUCCESS",
        "result": {"ok": True},
        "error_message": None,
    }
    path.write_text(json.dumps([record, record]), encoding="utf-8")
    with pytest.raises(OutboxError, match="duplicate"):
        ResultOutbox(path)

    record["result"] = None
    path.write_text(json.dumps([record]), encoding="utf-8")
    with pytest.raises(OutboxError, match="malformed"):
        ResultOutbox(path)


def test_json_logs_drop_secret_named_fields() -> None:
    record = logging.LogRecord("kandor", logging.INFO, "", 0, "safe", (), None)
    record.agent_id = "visible"
    record.agent_credential = "must-not-appear"
    record.enrollment_token = "must-not-appear"

    payload = JsonFormatter().format(record)

    assert "visible" in payload
    assert "must-not-appear" not in payload
    assert "credential" not in payload
    assert "token" not in payload


def test_rotating_log_file_is_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "agent.jsonl"
    handler = SecureRotatingFileHandler(path, maxBytes=100, backupCount=1, encoding="utf-8")
    try:
        handler.emit(logging.LogRecord("kandor", logging.INFO, "", 0, "event", (), None))
    finally:
        handler.close()
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
