"""add agent_name to knowledge_entries

Revision ID: 007
Revises: 006
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("knowledge_entries", sa.Column("agent_name", sa.String(128), nullable=True))
    op.create_index("ix_knowledge_entries_agent_name", "knowledge_entries", ["agent_name"])
    op.drop_index("ix_knowledge_entries_title", table_name="knowledge_entries")
    op.create_index("ix_knowledge_entries_title", "knowledge_entries", ["title"])
    op.drop_constraint("knowledge_entries_title_key", "knowledge_entries", type_="unique")
    op.create_unique_constraint("uq_knowledge_title_agent", "knowledge_entries", ["title", "agent_name"])


def downgrade():
    op.drop_constraint("uq_knowledge_title_agent", "knowledge_entries", type_="unique")
    op.create_unique_constraint("knowledge_entries_title_key", "knowledge_entries", ["title"])
    op.drop_index("ix_knowledge_entries_agent_name", table_name="knowledge_entries")
    op.drop_column("knowledge_entries", "agent_name")
