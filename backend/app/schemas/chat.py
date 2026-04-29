from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from app.schemas.message import MessageResponse


class ChatCreate(BaseModel):
    title: Optional[str] = "New Chat"


class ChatResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatDetailResponse(ChatResponse):
    messages: list[MessageResponse] = []
