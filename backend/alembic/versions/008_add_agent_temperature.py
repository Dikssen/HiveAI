"""add temperature to agents

Revision ID: 008
Revises: 007
Create Date: 2026-05-12
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agents",
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.7"),
    )


def downgrade():
    op.drop_column("agents", "temperature")
