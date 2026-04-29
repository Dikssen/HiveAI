from sqlalchemy.orm import Session

from app.config import settings
from app.orchestrator.base import BaseOrchestrator


def get_orchestrator(db: Session) -> BaseOrchestrator:
    if settings.ORCHESTRATOR_RUNNER == "langgraph":
        from app.orchestrator.graph import LangGraphOrchestrator
        return LangGraphOrchestrator(db)
    from app.orchestrator.orchestrator import Orchestrator
    return Orchestrator(db)
