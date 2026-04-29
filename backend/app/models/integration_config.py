from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from app.db.base import Base


class IntegrationConfig(Base):
    __tablename__ = "integration_configs"

    id = Column(Integer, primary_key=True)
    key = Column(String(128), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    is_secret = Column(Boolean, default=False, nullable=False)
    description = Column(String(256), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
