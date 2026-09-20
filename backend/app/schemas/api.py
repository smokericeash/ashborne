from __future__ import annotations

import ipaddress
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SecretStr,
    StrictBool,
    field_validator,
    model_validator,
)

from app.models import AgentStatus, RoleName, TaskStatus, TaskType


def normalize_email_address(value: Any) -> str:
    """Validate an account address while supporting the documented lab-only .local domain.

    ``email-validator`` intentionally rejects special-use domains such as ``.local``.
    ASHBORNE's required demo identities use ``example.local``, so local domains are
    syntax-checked against an equivalent reserved ``.example`` name and then kept
    unchanged. Public addresses still receive the library's full syntax validation.
    Deliverability checks are never appropriate for a self-hosted login identifier.
    """

    if not isinstance(value, str):
        raise ValueError("email address must be a string")
    candidate = value.strip()
    local_part, separator, domain = candidate.rpartition("@")
    try:
        if separator and domain.casefold().endswith(".local"):
            probe_domain = f"{domain[: -len('.local')]}.example"
            validate_email(f"{local_part}@{probe_domain}", check_deliverability=False, test_environment=True)
            normalized = f"{local_part}@{domain}"
        else:
            normalized = validate_email(candidate, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc
    return normalized.casefold()


EmailAddress = Annotated[
    str,
    BeforeValidator(normalize_email_address),
    Field(min_length=3, max_length=320),
]


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", populate_by_name=True)


class MessageResponse(APIModel):
    message: str


class UserResponse(APIModel):
    id: str
    email: EmailAddress
    display_name: str
    role: RoleName
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class UserCreate(APIModel):
    email: EmailAddress
    display_name: str = Field(min_length=1, max_length=120)
    password: SecretStr
    role: RoleName = RoleName.VIEWER

    @field_validator("display_name")
    @classmethod
    def normalized_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("display name cannot be blank")
        return normalized

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if len(raw) < 12 or len(raw) > 128:
            raise ValueError("password must be between 12 and 128 characters")
        if not (any(c.islower() for c in raw) and any(c.isupper() for c in raw) and any(c.isdigit() for c in raw)):
            raise ValueError("password must include upper-case, lower-case, and numeric characters")
        return value


class UserUpdate(APIModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: RoleName | None = None
    is_active: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_nulls(cls, value: Any) -> Any:
        if isinstance(value, dict) and any(field_value is None for field_value in value.values()):
            raise ValueError("update fields may not be null")
        return value

    @field_validator("display_name")
    @classmethod
    def normalized_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("display name cannot be blank")
        return normalized

    @model_validator(mode="after")
    def nonempty(self) -> UserUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class UserList(APIModel):
    items: list[UserResponse]
    total: int
    skip: int
    limit: int


class LoginRequest(APIModel):
    email: EmailAddress
    password: SecretStr


class RefreshRequest(APIModel):
    refresh_token: SecretStr


class LogoutRequest(RefreshRequest):
    pass


class TokenResponse(APIModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 -- protocol token type, not a credential
    expires_in: int
    user: UserResponse


class AgentIdentity(APIModel):
    agent_id: str
    name: str | None = Field(default=None, max_length=120)
    hostname: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=255)
    operating_system: str = Field(min_length=1, max_length=120)
    os_version: str = Field(default="", max_length=255)
    architecture: str = Field(min_length=1, max_length=64)
    agent_version: str = Field(min_length=1, max_length=64)
    ip_address: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("agent_id")
    @classmethod
    def valid_uuid(cls, value: str) -> str:
        try:
            return str(uuid.UUID(value))
        except ValueError as exc:
            raise ValueError("agent_id must be a valid UUID") from exc

    @field_validator("ip_address")
    @classmethod
    def valid_ip(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        try:
            return str(ipaddress.ip_address(value))
        except ValueError as exc:
            raise ValueError("ip_address must be a valid IPv4 or IPv6 address") from exc

    @field_validator("tags")
    @classmethod
    def valid_tags(cls, tags: list[str]) -> list[str]:
        normalized: list[str] = []
        for tag in tags:
            cleaned = tag.strip().lower()
            if not cleaned or len(cleaned) > 40 or not all(c.isalnum() or c in "-_." for c in cleaned):
                raise ValueError("tags must be 1-40 characters using letters, digits, dash, underscore, or dot")
            if cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    @model_validator(mode="after")
    def fill_name(self) -> AgentIdentity:
        if self.name is None:
            self.name = self.hostname
        return self


class AgentEnrollRequest(AgentIdentity):
    token: SecretStr


class DemoAgentEnrollRequest(AgentIdentity):
    pass


class AgentResponse(APIModel):
    id: str
    agent_id: str
    name: str
    hostname: str
    username: str
    operating_system: str
    os_version: str
    architecture: str
    ip_address: str | None
    agent_version: str
    first_seen: datetime
    last_seen: datetime | None
    status: AgentStatus
    tags: list[str]
    uptime_seconds: int | None = None


class AgentEnrollmentResponse(APIModel):
    agent: AgentResponse
    credential: str
    credential_type: Literal["bearer"] = "bearer"


class AgentList(APIModel):
    items: list[AgentResponse]
    total: int
    skip: int
    limit: int


class EnrollmentTokenCreate(APIModel):
    expires_in_seconds: int = Field(default=900, ge=60, le=86_400)
    description: str | None = Field(default=None, max_length=255)


class EnrollmentTokenResponse(APIModel):
    id: str
    prefix: str
    description: str | None
    created_by_id: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None
    used_by_agent_id: str | None
    revoked_at: datetime | None
    token: str | None = None


class EnrollmentTokenList(APIModel):
    items: list[EnrollmentTokenResponse]
    total: int
    skip: int
    limit: int


class HeartbeatRequest(APIModel):
    timestamp: datetime | None = None
    agent_version: str = Field(min_length=1, max_length=64)
    uptime_seconds: int | None = Field(default=None, ge=0)
    hostname: str = Field(min_length=1, max_length=255)
    ip_address: str | None = None
    health: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ip_address")
    @classmethod
    def valid_ip(cls, value: str | None) -> str | None:
        return AgentIdentity.valid_ip(value)

    @field_validator("health")
    @classmethod
    def limited_health(cls, value: dict[str, Any]) -> dict[str, Any]:
        import json

        if len(value) > 30:
            raise ValueError("health payload has too many fields")
        try:
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("health payload must contain finite JSON values") from exc
        if len(encoded) > 16_384:
            raise ValueError("health payload is too large")
        return value


class HeartbeatResponse(APIModel):
    status: AgentStatus
    last_seen: datetime
    next_heartbeat_seconds: int


class HeartbeatItem(APIModel):
    id: str
    received_at: datetime
    reported_at: datetime | None
    uptime_seconds: int | None
    agent_version: str
    hostname: str
    ip_address: str | None
    health: dict[str, Any]


class AgentDetail(AgentResponse):
    recent_heartbeats: list[HeartbeatItem] = Field(default_factory=list)
    recent_tasks: list[TaskResponse] = Field(default_factory=list)


class TaskCreate(APIModel):
    agent_id: str
    task_type: TaskType
    parameters: dict[str, Any] = Field(default_factory=dict)
    authorized_scope_confirmed: StrictBool
    expires_in_seconds: int | None = Field(default=None, ge=60, le=604_800)

    @field_validator("agent_id")
    @classmethod
    def valid_uuid(cls, value: str) -> str:
        return AgentIdentity.valid_uuid(value)

    @field_validator("authorized_scope_confirmed")
    @classmethod
    def scope_must_be_confirmed(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("authorized lab scope must be explicitly confirmed")
        return value


class TaskResultSubmission(APIModel):
    status: Literal["SUCCESS", "FAILED"]
    result: dict[str, Any] | None = None
    error_message: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def consistent(self) -> TaskResultSubmission:
        import json

        if self.status == "SUCCESS" and self.result is None:
            raise ValueError("successful tasks require a structured result")
        if self.status == "SUCCESS" and self.error_message:
            raise ValueError("successful tasks cannot include an error message")
        if self.status == "FAILED" and not self.error_message:
            raise ValueError("failed tasks require an error message")
        try:
            encoded_result = (
                json.dumps(self.result, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
                if self.result is not None
                else b""
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("task result must contain finite JSON values") from exc
        if len(encoded_result) > 524_288:
            raise ValueError("task result exceeds 512 KiB")
        return self


class TaskResponse(APIModel):
    id: str
    agent_id: str
    agent_name: str | None = None
    task_type: TaskType
    parameters: dict[str, Any]
    requested_by_id: str | None
    requested_by: str | None = None
    requested_by_email: EmailAddress | None = None
    created_at: datetime
    expires_at: datetime
    dispatched_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    status: TaskStatus
    result: dict[str, Any] | None = None
    error_message: str | None = None


class TaskList(APIModel):
    items: list[TaskResponse]
    total: int
    skip: int
    limit: int
    count: int | None = None


class AuditResponse(APIModel):
    id: str
    timestamp: datetime
    event_type: str
    user_id: str | None
    user_email: EmailAddress | None = None
    agent_id: str | None
    agent_name: str | None = None
    source_ip: str | None
    request_id: str | None
    metadata: dict[str, Any]


class AuditList(APIModel):
    items: list[AuditResponse]
    total: int
    skip: int
    limit: int


class DashboardMetrics(APIModel):
    total_agents: int
    online_agents: int
    degraded_agents: int
    offline_agents: int
    tasks_queued: int
    tasks_running: int
    tasks_completed: int
    tasks_failed: int
    task_success_rate: float
    average_checkin_interval_seconds: float | None
    os_distribution: dict[str, int]
    version_distribution: dict[str, int]
    tasks_over_time: list[dict[str, Any]]
    heartbeat_activity: list[dict[str, Any]]


class ActivityResponse(APIModel):
    agents: list[AgentResponse]
    tasks: list[TaskResponse]
    audit_events: list[AuditResponse]


class SettingsResponse(APIModel):
    heartbeat_interval_seconds: int
    degraded_threshold_seconds: int
    offline_threshold_seconds: int
    task_expiration_seconds: int
    session_timeout_minutes: int
    page_size: int
    audit_retention_days: int


class SettingsUpdate(APIModel):
    heartbeat_interval_seconds: int | None = Field(default=None, ge=5, le=3600)
    degraded_threshold_seconds: int | None = Field(default=None, ge=10, le=86400)
    offline_threshold_seconds: int | None = Field(default=None, ge=20, le=604800)
    task_expiration_seconds: int | None = Field(default=None, ge=60, le=604800)
    session_timeout_minutes: int | None = Field(default=None, ge=5, le=1440)
    page_size: int | None = Field(default=None, ge=1, le=500)
    audit_retention_days: int | None = Field(default=None, ge=30, le=3650)

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_nulls(cls, value: Any) -> Any:
        if isinstance(value, dict) and any(field_value is None for field_value in value.values()):
            raise ValueError("setting values may not be null")
        return value

    @model_validator(mode="after")
    def nonempty(self) -> SettingsUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one setting is required")
        return self


AgentDetail.model_rebuild()
