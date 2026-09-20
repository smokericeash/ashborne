"""Create the initial ASHBORNE application schema.

Revision ID: 20260914_0001
Revises:
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

role_name = sa.Enum(
    "ADMINISTRATOR",
    "OPERATOR",
    "VIEWER",
    name="rolename",
    native_enum=False,
)
agent_status = sa.Enum(
    "ONLINE",
    "DEGRADED",
    "OFFLINE",
    name="agentstatus",
    native_enum=False,
)
task_type = sa.Enum(
    "QUICK_RECON",
    "SYSTEM_INFO",
    "HOSTNAME",
    "CURRENT_USER",
    "SECURITY_CONTEXT",
    "CPU_INFO",
    "MEMORY_USAGE",
    "DISK_USAGE",
    "FILE_SYSTEM_OVERVIEW",
    "NETWORK_INTERFACES",
    "NETWORK_CONNECTIONS",
    "ROUTE_TABLE",
    "UPTIME",
    "PROCESS_INVENTORY",
    "INSTALLED_SOFTWARE",
    "LISTENING_PORTS",
    "AGENT_HEALTH",
    "PING",
    name="tasktype",
    native_enum=False,
)
task_status = sa.Enum(
    "QUEUED",
    "DISPATCHED",
    "RUNNING",
    "SUCCESS",
    "FAILED",
    "CANCELLED",
    "EXPIRED",
    name="taskstatus",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("name", role_name, nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("operating_system", sa.String(length=120), nullable=False),
        sa.Column("os_version", sa.String(length=255), nullable=False),
        sa.Column("architecture", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("agent_version", sa.String(length=64), nullable=False),
        sa.Column("status", agent_status, nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_uptime_seconds", sa.Integer(), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agents_agent_version", "agents", ["agent_version"])
    op.create_index("ix_agents_hostname", "agents", ["hostname"])
    op.create_index("ix_agents_ip_address", "agents", ["ip_address"])
    op.create_index("ix_agents_last_seen", "agents", ["last_seen"])
    op.create_index("ix_agents_name", "agents", ["name"])
    op.create_index("ix_agents_operating_system", "agents", ["operating_system"])
    op.create_index("ix_agents_removed_at", "agents", ["removed_at"])
    op.create_index("ix_agents_status", "agents", ["status"])

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", role_name, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["role"], ["roles.name"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "agent_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("credential_hash", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_credentials_agent_id", "agent_credentials", ["agent_id"])
    op.create_index(
        "ix_agent_credentials_credential_hash",
        "agent_credentials",
        ["credential_hash"],
        unique=True,
    )
    op.create_index("ix_agent_credentials_revoked_at", "agent_credentials", ["revoked_at"])

    op.create_table(
        "enrollment_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by_agent_id", sa.String(length=36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_enrollment_tokens_created_by_id", "enrollment_tokens", ["created_by_id"])
    op.create_index("ix_enrollment_tokens_expires_at", "enrollment_tokens", ["expires_at"])
    op.create_index("ix_enrollment_tokens_revoked_at", "enrollment_tokens", ["revoked_at"])
    op.create_index("ix_enrollment_tokens_used_at", "enrollment_tokens", ["used_at"])

    op.create_table(
        "heartbeats",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uptime_seconds", sa.Integer(), nullable=True),
        sa.Column("agent_version", sa.String(length=64), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("health", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_heartbeats_agent_id", "heartbeats", ["agent_id"])
    op.create_index("ix_heartbeats_agent_received", "heartbeats", ["agent_id", "received_at"])
    op.create_index("ix_heartbeats_received_at", "heartbeats", ["received_at"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("jti_hash", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index("ix_refresh_tokens_jti_hash", "refresh_tokens", ["jti_hash"], unique=True)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("task_type", task_type, nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("requested_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", task_status, nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_agent_id", "tasks", ["agent_id"])
    op.create_index("ix_tasks_agent_status_created", "tasks", ["agent_id", "status", "created_at"])
    op.create_index("ix_tasks_created_at", "tasks", ["created_at"])
    op.create_index("ix_tasks_expires_at", "tasks", ["expires_at"])
    op.create_index("ix_tasks_requested_by_id", "tasks", ["requested_by_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_task_type", "tasks", ["task_type"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("source_ip", sa.String(length=45), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_agent_id", "audit_events", ["agent_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])
    op.create_index("ix_audit_events_source_ip", "audit_events", ["source_ip"])
    op.create_index("ix_audit_events_timestamp", "audit_events", ["timestamp"])
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])

    op.create_table(
        "task_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_results_task_id", "task_results", ["task_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_task_results_task_id", table_name="task_results")
    op.drop_table("task_results")
    op.drop_index("ix_audit_events_user_id", table_name="audit_events")
    op.drop_index("ix_audit_events_timestamp", table_name="audit_events")
    op.drop_index("ix_audit_events_source_ip", table_name="audit_events")
    op.drop_index("ix_audit_events_request_id", table_name="audit_events")
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_agent_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_tasks_task_type", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_requested_by_id", table_name="tasks")
    op.drop_index("ix_tasks_expires_at", table_name="tasks")
    op.drop_index("ix_tasks_created_at", table_name="tasks")
    op.drop_index("ix_tasks_agent_status_created", table_name="tasks")
    op.drop_index("ix_tasks_agent_id", table_name="tasks")
    op.drop_table("tasks")
    op.drop_table("settings")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_jti_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_heartbeats_received_at", table_name="heartbeats")
    op.drop_index("ix_heartbeats_agent_received", table_name="heartbeats")
    op.drop_index("ix_heartbeats_agent_id", table_name="heartbeats")
    op.drop_table("heartbeats")
    op.drop_index("ix_enrollment_tokens_used_at", table_name="enrollment_tokens")
    op.drop_index("ix_enrollment_tokens_revoked_at", table_name="enrollment_tokens")
    op.drop_index("ix_enrollment_tokens_expires_at", table_name="enrollment_tokens")
    op.drop_index("ix_enrollment_tokens_created_by_id", table_name="enrollment_tokens")
    op.drop_table("enrollment_tokens")
    op.drop_index("ix_agent_credentials_revoked_at", table_name="agent_credentials")
    op.drop_index("ix_agent_credentials_credential_hash", table_name="agent_credentials")
    op.drop_index("ix_agent_credentials_agent_id", table_name="agent_credentials")
    op.drop_table("agent_credentials")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_agents_status", table_name="agents")
    op.drop_index("ix_agents_removed_at", table_name="agents")
    op.drop_index("ix_agents_operating_system", table_name="agents")
    op.drop_index("ix_agents_name", table_name="agents")
    op.drop_index("ix_agents_last_seen", table_name="agents")
    op.drop_index("ix_agents_ip_address", table_name="agents")
    op.drop_index("ix_agents_hostname", table_name="agents")
    op.drop_index("ix_agents_agent_version", table_name="agents")
    op.drop_table("agents")
    op.drop_table("roles")
