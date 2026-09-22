"""Route generic operations through a Kali controller agent.

Revision ID: 20260920_0003
Revises: 20260920_0002
Create Date: 2026-09-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_0003"
down_revision: str | None = "20260920_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _batch_options() -> dict[str, str]:
    return {"recreate": "always"} if op.get_bind().dialect.name == "sqlite" else {}


def upgrade() -> None:
    with op.batch_alter_table("tasks", **_batch_options()) as batch_op:
        batch_op.add_column(sa.Column("executor_agent_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_tasks_executor_agent_id_agents",
            "agents",
            ["executor_agent_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_tasks_executor_agent_id", ["executor_agent_id"], unique=False)
        batch_op.create_index(
            "ix_tasks_executor_status_created",
            ["executor_agent_id", "status", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("tasks", **_batch_options()) as batch_op:
        batch_op.drop_index("ix_tasks_executor_status_created")
        batch_op.drop_index("ix_tasks_executor_agent_id")
        batch_op.drop_constraint("fk_tasks_executor_agent_id_agents", type_="foreignkey")
        batch_op.drop_column("executor_agent_id")
