from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.agent_run import AgentRun
from app.models.worker_log import WorkerLog
from app.schemas.agent_run import AgentRunResponse, WorkerLogResponse

router = APIRouter(tags=["agent_runs"])


@router.get("/chats/{chat_id}/agent-runs", response_model=list[AgentRunResponse])
def get_chat_agent_runs(chat_id: int, db: Session = Depends(get_db)):
    """Return all agent runs for a chat, ordered by creation time."""
    return (
        db.query(AgentRun)
        .filter(AgentRun.chat_id == chat_id)
        .order_by(AgentRun.created_at)
        .all()
    )


@router.get("/agent-runs/{agent_run_id}", response_model=AgentRunResponse)
def get_agent_run(agent_run_id: int, db: Session = Depends(get_db)):
    ar = db.query(AgentRun).filter(AgentRun.id == agent_run_id).first()
    if not ar:
        raise HTTPException(status_code=404, detail="AgentRun not found")
    return ar


@router.get("/agent-runs/{agent_run_id}/logs", response_model=list[WorkerLogResponse])
def get_agent_run_logs(agent_run_id: int, db: Session = Depends(get_db)):
    """Return all worker logs for a specific agent run."""
    return (
        db.query(WorkerLog)
        .filter(WorkerLog.agent_run_id == agent_run_id)
        .order_by(WorkerLog.created_at)
        .all()
    )
