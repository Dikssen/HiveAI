"""add integration_configs table

Revision ID: 005
Revises: 004
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "integration_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("description", sa.String(256), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("integration_configs")
