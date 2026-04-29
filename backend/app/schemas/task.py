from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class TaskResponse(BaseModel):
    id: int
    chat_id: int
    celery_task_id: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SendMessageResponse(BaseModel):
    message_id: int
    task_id: int
    status: str
