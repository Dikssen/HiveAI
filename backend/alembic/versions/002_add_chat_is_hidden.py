"""add is_hidden to chats

Revision ID: 002
Revises: 001
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "chats",
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade():
    op.drop_column("chats", "is_hidden")
