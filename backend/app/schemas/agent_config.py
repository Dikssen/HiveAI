from datetime import datetime
from pydantic import BaseModel


class ToolConfigResponse(BaseModel):
    id: int
    tool_name: str
    is_enabled: bool

    class Config:
        from_attributes = True


class AgentResponse(BaseModel):
    id: int
    name: str
    role: str
    description: str | None
    is_enabled: bool
    temperature: float
    tool_configs: list[ToolConfigResponse] = []

    class Config:
        from_attributes = True


class ToolConfigUpdate(BaseModel):
    is_enabled: bool


class AgentUpdate(BaseModel):
    is_enabled: bool | None = None
    temperature: float | None = None
