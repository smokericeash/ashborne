from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from typer.testing import CliRunner

from app.cli import cli
from app.core.config import BACKEND_DIRECTORY, PROJECT_DIRECTORY, Settings
from app.core.database import Base, SessionLocal, engine
from app.core.events import EventBroker
from app.core.logging import JsonFormatter
from app.core.time import utcnow
from app.models import User
from app.services.seed import seed_development
from tests.conftest import authorization


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "database_url": "postgresql+asyncpg://ashborne:random-password@database:5432/ashborne",
        "secret_key": "unique-production-signing-key-with-more-than-32-characters",
        "cors_origins": ["https://ashborne.example"],
        "trusted_hosts": ["ashborne.example"],
        "auto_create_tables": False,
        "seed_development": False,
        "admin_password": None,
        "operator_password": None,
        "viewer_password": None,
        "demo_bootstrap_secret": None,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_configuration_accepts_only_explicit_safe_values() -> None:
    settings = production_settings()
    assert settings.environment == "production"

    unsafe_values = [
        {"secret_key": "CHANGE_ME_64_character_random_signing_secret_0000000000000000000000"},
        {"database_url": "postgresql+asyncpg://ashborne:CHANGE_ME_password@database:5432/ashborne"},
        {"redis_url": "redis://:CHANGE_ME_password@redis:6379/0"},
        {"trusted_hosts": ["*"]},
        {"trusted_hosts": []},
        {"seed_development": True},
        {"demo_bootstrap_secret": "configured-demo-secret"},
        {"admin_password": "configured-development-password"},
        {"auto_create_tables": True},
    ]
    for unsafe in unsafe_values:
        with pytest.raises(ValidationError):
            production_settings(**unsafe)


def test_blank_optional_compose_secrets_are_treated_as_unset() -> None:
    settings = production_settings(
        admin_password="",
        operator_password="   ",
        viewer_password="",
        demo_bootstrap_secret="",
    )
    assert settings.admin_password is None
    assert settings.operator_password is None
    assert settings.viewer_password is None
    assert settings.demo_bootstrap_secret is None


def test_dotenv_locations_are_repository_relative() -> None:
    root_env, backend_env = Settings.model_config["env_file"]
    assert root_env == PROJECT_DIRECTORY / ".env"
    assert backend_env == BACKEND_DIRECTORY / ".env"


def test_comma_separated_list_environment_values_are_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASHBORNE_CORS_ORIGINS", "https://one.example, https://two.example")
    monkeypatch.setenv("ASHBORNE_TRUSTED_HOSTS", "one.example,two.example")

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["https://one.example", "https://two.example"]
    assert settings.trusted_hosts == ["one.example", "two.example"]


async def test_local_event_broker_delivers_without_redis() -> None:
    broker = EventBroker(max_queue_size=2)
    stream = broker.subscribe()
    pending = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    await broker.publish("task.created", {"task_id": "test-task"})
    event = await asyncio.wait_for(pending, timeout=1)
    assert event["event"] == "task.created"
    assert event["data"] == {"task_id": "test-task"}
    await stream.aclose()
    await broker.close()


async def test_development_seed_rejects_weak_account_passwords() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        seed_development=True,
        admin_password="all-lowercase-password",
    )
    async with SessionLocal() as db:
        with pytest.raises(RuntimeError, match="upper-case"):
            await seed_development(db, settings)
        await db.rollback()


def test_json_logging_redacts_credentials_tokens_and_url_passwords() -> None:
    record = logging.LogRecord(
        "ashborne.test",
        logging.ERROR,
        __file__,
        1,
        (
            "authorization=Bearer header-value password='plain-value' "
            "credential=kac_example-token token=ket_example.token "
            "url=postgresql://user:database-password@database/ashborne"
        ),
        (),
        None,
    )
    payload = json.loads(JsonFormatter().format(record))
    rendered = payload["message"]
    for secret in ("header-value", "plain-value", "kac_example-token", "ket_example.token", "database-password"):
        assert secret not in rendered
    assert "[redacted]" in rendered


async def test_audit_rejects_inverted_time_range(client: httpx.AsyncClient, admin_tokens: dict) -> None:
    response = await client.get(
        "/api/v1/audit",
        params={
            "start_time": utcnow().isoformat(),
            "end_time": (utcnow() - timedelta(days=1)).isoformat(),
        },
        headers=authorization(admin_tokens),
    )
    assert response.status_code == 422


async def _prepare_cli_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        await seed_development(db)
    await engine.dispose()


async def _user_count(email: str) -> int:
    async with SessionLocal() as db:
        count = (await db.execute(select(func.count(User.id)).where(User.email == email))).scalar_one()
    await engine.dispose()
    return count


def test_administrative_cli_status_and_create_user() -> None:
    asyncio.run(_prepare_cli_database())
    runner = CliRunner()

    status_result = runner.invoke(cli, ["status"])
    assert status_result.exit_code == 0, status_result.output
    status_payload = json.loads(status_result.output)
    assert status_payload["status"] == "ok"
    assert status_payload["users"] == 3
    asyncio.run(engine.dispose())

    create_result = runner.invoke(
        cli,
        [
            "create-user",
            "--email",
            "cli-user@example.local",
            "--display-name",
            "CLI User",
            "--role",
            "VIEWER",
            "--password",
            "CliUserPassword123!",
        ],
    )
    assert create_result.exit_code == 0, create_result.output
    assert "Created cli-user@example.local" in create_result.output
    asyncio.run(engine.dispose())
    assert asyncio.run(_user_count("cli-user@example.local")) == 1
