"""
Base tool class with structured metadata.
"""
import structlog
from typing import Optional
from pydantic import BaseModel

logger = structlog.get_logger()


class LoggedTool(BaseModel):
    """Base tool that logs every invocation."""
    name: str
    description: str
    args_schema: Optional[type] = None

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, *args, **kwargs):
        raise NotImplementedError
