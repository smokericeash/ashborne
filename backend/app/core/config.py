from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
PROJECT_DIRECTORY = BACKEND_DIRECTORY.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ASHBORNE_",
        # Resolve dotenv files from this module, not the process working directory.
        # This keeps `uvicorn app.main:app` and `uvicorn backend.app.main:app`
        # consistent when launched from the backend or repository root.
        env_file=(PROJECT_DIRECTORY / ".env", BACKEND_DIRECTORY / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ASHBORNE"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    database_url: str = "sqlite+aiosqlite:///./ashborne.db"
    redis_url: str | None = None
    secret_key: SecretStr = SecretStr("development-only-change-this-secret-key-please")
    jwt_issuer: str = "ashborne"
    jwt_audience: str = "ashborne-ui"
    session_timeout_minutes: int = Field(default=60, ge=5, le=1_440)
    refresh_token_days: int = Field(default=7, ge=1, le=90)
    # NoDecode lets the before-validator accept the documented comma-separated
    # environment syntax as well as JSON arrays and direct Python lists.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://localhost:5173"]
    trusted_hosts: Annotated[list[str], NoDecode] = ["*"]
    max_request_bytes: int = Field(default=1_048_576, ge=1_024, le=10_485_760)
    rate_limit_requests: int = Field(default=300, ge=10, le=100_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3_600)
    login_rate_limit_requests: int = Field(default=10, ge=1, le=1_000)
    heartbeat_interval_seconds: int = Field(default=30, ge=5, le=3_600)
    degraded_threshold_seconds: int = Field(default=60, ge=10, le=86_400)
    offline_threshold_seconds: int = Field(default=300, ge=20, le=604_800)
    task_expiration_seconds: int = Field(default=3_600, ge=60, le=604_800)
    kali_controller_agent_id: str | None = None
    page_size: int = Field(default=50, ge=1, le=500)
    audit_retention_days: int = Field(default=365, ge=30, le=3_650)
    auto_create_tables: bool = True
    seed_development: bool = False
    admin_password: SecretStr | None = None
    operator_password: SecretStr | None = None
    viewer_password: SecretStr | None = None
    demo_bootstrap_secret: SecretStr | None = None
    log_level: str = "INFO"

    @field_validator("cors_origins", "trusted_hosts", mode="before")
    @classmethod
    def parse_list(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                return json.loads(value)
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if value.startswith("sqlite:///") and not value.startswith("sqlite+aiosqlite:///"):
            return value.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        return value

    @field_validator(
        "admin_password",
        "operator_password",
        "viewer_password",
        "demo_bootstrap_secret",
        mode="before",
    )
    @classmethod
    def blank_optional_secret_is_none(cls, value: Any) -> Any:
        """Treat Compose's deliberately blank optional variables as unset."""

        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("kali_controller_agent_id")
    @classmethod
    def valid_optional_agent_id(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        try:
            return str(uuid.UUID(value))
        except ValueError as exc:
            raise ValueError("ASHBORNE_KALI_CONTROLLER_AGENT_ID must be a UUID") from exc

    @model_validator(mode="after")
    def validate_security(self) -> Settings:
        if self.degraded_threshold_seconds >= self.offline_threshold_seconds:
            raise ValueError("degraded threshold must be lower than offline threshold")
        if self.environment == "production":
            secret = self.secret_key.get_secret_value()
            configured_secrets = {
                "ASHBORNE_SECRET_KEY": secret,
                "ASHBORNE_DATABASE_URL": self.database_url,
                "ASHBORNE_REDIS_URL": self.redis_url or "",
            }
            placeholders = [name for name, value in configured_secrets.items() if "change_me" in value.casefold()]
            if placeholders:
                raise ValueError(f"production configuration contains CHANGE_ME placeholders: {', '.join(placeholders)}")
            if len(secret) < 32 or secret.lower().startswith(("development-only", "changeme")):
                raise ValueError("ASHBORNE_SECRET_KEY must be a unique 32+ character value in production")
            if self.debug:
                raise ValueError("debug mode cannot be enabled in production")
            if "*" in self.cors_origins:
                raise ValueError("wildcard CORS origins are forbidden in production")
            if (
                not self.trusted_hosts
                or "*" in self.trusted_hosts
                or any(not host.strip() for host in self.trusted_hosts)
            ):
                raise ValueError("ASHBORNE_TRUSTED_HOSTS must be explicit in production")
            if not self.database_url.startswith("postgresql+asyncpg://"):
                raise ValueError("production requires a PostgreSQL asyncpg database URL")
            development_passwords = (self.admin_password, self.operator_password, self.viewer_password)
            if (
                self.seed_development
                or self.demo_bootstrap_secret is not None
                or any(password is not None for password in development_passwords)
            ):
                raise ValueError("development seed and demo enrollment must be disabled in production")
            if self.auto_create_tables:
                raise ValueError(
                    "ASHBORNE_AUTO_CREATE_TABLES must be false in production; apply Alembic migrations instead"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
