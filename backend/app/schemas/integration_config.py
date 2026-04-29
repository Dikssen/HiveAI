from datetime import datetime
from typing import Optional
from pydantic import BaseModel, model_validator


class IntegrationConfigResponse(BaseModel):
    id: int
    key: str
    value: Optional[str]
    is_secret: bool
    description: Optional[str]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

    @model_validator(mode="after")
    def mask_secret(self):
        if self.is_secret and self.value:
            self.value = "***"
        return self


class IntegrationConfigUpdate(BaseModel):
    value: Optional[str] = None
