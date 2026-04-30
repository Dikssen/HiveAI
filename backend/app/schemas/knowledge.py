from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class KnowledgeEntryResponse(BaseModel):
    id: int
    title: str
    content: str
    tags: Optional[str]
    agent_name: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class KnowledgeEntryListResponse(BaseModel):
    id: int
    title: str
    tags: Optional[str]
    agent_name: Optional[str]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class KnowledgeEntryCreate(BaseModel):
    title: str
    content: str
    tags: Optional[str] = None
    agent_name: Optional[str] = None


class KnowledgeEntryUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[str] = None
    agent_name: Optional[str] = None
