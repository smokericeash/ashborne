"""Add bulk task grouping and expanded bounded task types.

Revision ID: 20260920_0002
Revises: 20260914_0001
Create Date: 2026-09-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_0002"
down_revision: str | None = "20260914_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PREVIOUS_TASK_TYPES = (
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
)

ADDED_TASK_TYPES = (
    "LINUX_KERNEL_INFO",
    "LINUX_IDENTITY",
    "GROUP_MEMBERSHIP",
    "LINUX_CAPABILITIES",
    "LINUX_MOUNTS",
    "SAFE_ENVIRONMENT_OVERVIEW",
    "SERVICE_OVERVIEW",
    "SCHEDULED_ACTIVITY_OVERVIEW",
    "PRIVILEGE_ENUMERATION",
    "NETWORK_OVERVIEW",
    "HOST_RECON",
)

previous_task_type = sa.Enum(
    *PREVIOUS_TASK_TYPES,
    name="tasktype",
    native_enum=False,
    create_constraint=False,
)
expanded_task_type = sa.Enum(
    *PREVIOUS_TASK_TYPES,
    *ADDED_TASK_TYPES,
    name="tasktype",
    native_enum=False,
    create_constraint=False,
)


def _batch_options() -> dict[str, str]:
    # SQLite cannot alter a VARCHAR width or add a named unique constraint in
    # place. Alembic's batch recreation preserves the existing rows and FKs.
    return {"recreate": "always"} if op.get_bind().dialect.name == "sqlite" else {}


def upgrade() -> None:
    with op.batch_alter_table("tasks", **_batch_options()) as batch_op:
        batch_op.alter_column(
            "task_type",
            existing_type=previous_task_type,
            type_=expanded_task_type,
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column("bulk_operation_id", sa.String(length=36), nullable=True))
        batch_op.create_unique_constraint("uq_tasks_bulk_agent", ["bulk_operation_id", "agent_id"])
        batch_op.create_index("ix_tasks_bulk_operation_id", ["bulk_operation_id"], unique=False)
        batch_op.create_index("ix_tasks_bulk_created", ["bulk_operation_id", "created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    placeholders = ", ".join(f":task_type_{index}" for index, _ in enumerate(ADDED_TASK_TYPES))
    parameters = {f"task_type_{index}": task_type for index, task_type in enumerate(ADDED_TASK_TYPES)}
    used_new_types = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM tasks WHERE task_type IN ({placeholders})"),  # noqa: S608
        parameters,
    ).scalar_one()
    if used_new_types:
        raise RuntimeError("cannot downgrade while tasks use task types introduced by 20260920_0002")

    with op.batch_alter_table("tasks", **_batch_options()) as batch_op:
        batch_op.drop_index("ix_tasks_bulk_created")
        batch_op.drop_index("ix_tasks_bulk_operation_id")
        batch_op.drop_constraint("uq_tasks_bulk_agent", type_="unique")
        batch_op.drop_column("bulk_operation_id")
        batch_op.alter_column(
            "task_type",
            existing_type=expanded_task_type,
            type_=previous_task_type,
            existing_nullable=False,
        )
