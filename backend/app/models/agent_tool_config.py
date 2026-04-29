from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.db.base import Base


class AgentToolConfig(Base):
    __tablename__ = "agent_tool_configs"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name = Column(String(200), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("agent_id", "tool_name", name="uq_agent_tool"),
    )

    agent = relationship("Agent", back_populates="tool_configs")
