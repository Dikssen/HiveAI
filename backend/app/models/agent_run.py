from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, func
from sqlalchemy.orm import relationship

from app.db.base import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String(200), nullable=False)
    task_description = Column(Text, nullable=True)
    # pending / running / completed / failed
    status = Column(String(50), nullable=False, default="pending")
    input_payload = Column(JSON, nullable=True)
    output_payload = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    chat = relationship("Chat", back_populates="agent_runs")
    logs = relationship("WorkerLog", back_populates="agent_run", order_by="WorkerLog.created_at")
