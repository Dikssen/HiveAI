from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from app.db.base import Base


class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"

    id = Column(Integer, primary_key=True)
    title = Column(String(256), nullable=False, index=True)
    content = Column(Text, nullable=False)
    tags = Column(String(512), nullable=True)
    agent_name = Column(String(128), nullable=True, index=True)  # NULL = global
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("title", "agent_name", name="uq_knowledge_title_agent"),
    )
