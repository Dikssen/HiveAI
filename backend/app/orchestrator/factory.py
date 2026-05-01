from sqlalchemy.orm import Session

from app.config import settings
from app.orchestrator.base import BaseOrchestrator


def get_orchestrator(db: Session) -> BaseOrchestrator:
    if settings.ORCHESTRATOR_RUNNER == "langgraph":
        from app.orchestrator.graph import LangGraphOrchestrator
        return LangGraphOrchestrator(db)
    from app.orchestrator.orchestrator import Orchestrator
    return Orchestrator(db)


def get_streaming_orchestrator(db: Session):
    """
    Returns the streaming orchestrator matching ORCHESTRATOR_RUNNER config.

    custom    → StreamingOrchestrator            (async loop + token streaming)
    langgraph → StreamingLangGraphOrchestrator   (same streaming UX; .run() uses LangGraph graph)
    """
    from app.orchestrator.streaming_orchestrator import (
        StreamingOrchestrator,
        StreamingLangGraphOrchestrator,
    )
    if settings.ORCHESTRATOR_RUNNER == "langgraph":
        return StreamingLangGraphOrchestrator(db)
    return StreamingOrchestrator(db)
