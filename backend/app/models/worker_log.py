from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, func
from sqlalchemy.orm import relationship

from app.db.base import Base


class WorkerLog(Base):
    __tablename__ = "worker_logs"

    id = Column(Integer, primary_key=True, index=True)
    agent_run_id = Column(
        Integer, ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    worker_name = Column(String(200), nullable=True)
    level = Column(String(50), nullable=False, default="INFO")
    message = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    agent_run = relationship("AgentRun", back_populates="logs")
