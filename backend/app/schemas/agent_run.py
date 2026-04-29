from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


class WorkerLogResponse(BaseModel):
    id: int
    agent_run_id: Optional[int]
    worker_name: Optional[str]
    level: str
    message: str
    metadata_: Optional[Any] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AgentRunResponse(BaseModel):
    id: int
    chat_id: int
    agent_name: str
    task_description: Optional[str]
    status: str
    input_payload: Optional[Any]
    output_payload: Optional[Any]
    error: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime
    logs: list[WorkerLogResponse] = []

    class Config:
        from_attributes = True
