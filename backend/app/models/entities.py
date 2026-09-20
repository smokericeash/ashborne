from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, event
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def uuid4str() -> str:
    return str(uuid.uuid4())


class RoleName(enum.StrEnum):
    ADMINISTRATOR = "ADMINISTRATOR"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"


class AgentStatus(enum.StrEnum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


class TaskType(enum.StrEnum):
    QUICK_RECON = "QUICK_RECON"
    SYSTEM_INFO = "SYSTEM_INFO"
    HOSTNAME = "HOSTNAME"
    CURRENT_USER = "CURRENT_USER"
    SECURITY_CONTEXT = "SECURITY_CONTEXT"
    CPU_INFO = "CPU_INFO"
    MEMORY_USAGE = "MEMORY_USAGE"
    DISK_USAGE = "DISK_USAGE"
    FILE_SYSTEM_OVERVIEW = "FILE_SYSTEM_OVERVIEW"
    NETWORK_INTERFACES = "NETWORK_INTERFACES"
    NETWORK_CONNECTIONS = "NETWORK_CONNECTIONS"
    ROUTE_TABLE = "ROUTE_TABLE"
    UPTIME = "UPTIME"
    PROCESS_INVENTORY = "PROCESS_INVENTORY"
    INSTALLED_SOFTWARE = "INSTALLED_SOFTWARE"
    LISTENING_PORTS = "LISTENING_PORTS"
    AGENT_HEALTH = "AGENT_HEALTH"
    PING = "PING"


class TaskStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


enum_values = lambda enum_cls: [item.value for item in enum_cls]  # noqa: E731


class Role(Base):
    __tablename__ = "roles"
    name: Mapped[RoleName] = mapped_column(
        Enum(RoleName, native_enum=False, values_callable=enum_values), primary_key=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4str)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[RoleName] = mapped_column(
        Enum(RoleName, native_enum=False, values_callable=enum_values),
        ForeignKey("roles.name"),
        index=True,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    jti_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    family_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[str | None] = mapped_column(String(36))
    user: Mapped[User] = relationship()


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    operating_system: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    os_version: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    architecture: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), index=True)
    agent_version: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, native_enum=False, values_callable=enum_values),
        default=AgentStatus.OFFLINE,
        index=True,
        nullable=False,
    )
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_uptime_seconds: Mapped[int | None] = mapped_column(Integer)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    credentials: Mapped[list[AgentCredential]] = relationship(back_populates="agent", cascade="all, delete-orphan")
    heartbeats: Mapped[list[Heartbeat]] = relationship(back_populates="agent", cascade="all, delete-orphan")


class AgentCredential(Base):
    __tablename__ = "agent_credentials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4str)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True, nullable=False)
    credential_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    agent: Mapped[Agent] = relationship(back_populates="credentials")


class EnrollmentToken(Base):
    __tablename__ = "enrollment_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4str)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    used_by_agent_id: Mapped[str | None] = mapped_column(String(36))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class Heartbeat(Base):
    __tablename__ = "heartbeats"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4str)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uptime_seconds: Mapped[int | None] = mapped_column(Integer)
    agent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    health: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    agent: Mapped[Agent] = relationship(back_populates="heartbeats")
    __table_args__ = (Index("ix_heartbeats_agent_received", "agent_id", "received_at"),)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4str)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True, nullable=False)
    task_type: Mapped[TaskType] = mapped_column(
        Enum(TaskType, native_enum=False, values_callable=enum_values), index=True, nullable=False
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    requested_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, native_enum=False, values_callable=enum_values),
        default=TaskStatus.QUEUED,
        index=True,
        nullable=False,
    )
    agent: Mapped[Agent] = relationship()
    requested_by: Mapped[User | None] = relationship()
    result_record: Mapped[TaskResult | None] = relationship(
        back_populates="task", uselist=False, cascade="all, delete-orphan"
    )
    __table_args__ = (Index("ix_tasks_agent_status_created", "agent_id", "status", "created_at"),)


class TaskResult(Base):
    __tablename__ = "task_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4str)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    task: Mapped[Task] = relationship(back_populates="result_record")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4str)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    agent_id: Mapped[str | None] = mapped_column(String(36), index=True)
    source_ip: Mapped[str | None] = mapped_column(String(45), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    updated_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


@event.listens_for(Session, "before_flush")
def protect_audit_events(session: Session, flush_context, instances) -> None:
    if any(isinstance(obj, AuditEvent) for obj in session.deleted):
        raise ValueError("audit events are immutable")
    if any(isinstance(obj, AuditEvent) for obj in session.dirty):
        raise ValueError("audit events are immutable")
