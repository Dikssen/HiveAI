"""Add task_id and parent_run_id to agent_runs; add status index

Revision ID: 003
Revises: 002
Create Date: 2026-04-29 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("task_id", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("parent_run_id", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_agent_runs_task_id", "agent_runs", "tasks", ["task_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_agent_runs_parent_run_id", "agent_runs", "agent_runs", ["parent_run_id"], ["id"], ondelete="SET NULL"
    )

    op.create_index("ix_agent_runs_task_id", "agent_runs", ["task_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_tasks_chat_id", "tasks", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_chat_id", "tasks")
    op.drop_index("ix_agent_runs_status", "agent_runs")
    op.drop_index("ix_agent_runs_task_id", "agent_runs")
    op.drop_constraint("fk_agent_runs_parent_run_id", "agent_runs", type_="foreignkey")
    op.drop_constraint("fk_agent_runs_task_id", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "parent_run_id")
    op.drop_column("agent_runs", "task_id")
