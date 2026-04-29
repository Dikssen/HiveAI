from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.agent import Agent
from app.models.agent_tool_config import AgentToolConfig
from app.schemas.agent_config import AgentResponse, AgentUpdate, ToolConfigResponse, ToolConfigUpdate

router = APIRouter(prefix="/agents", tags=["agent_config"])


@router.get("", response_model=list[AgentResponse])
def list_agents(db: Session = Depends(get_db)):
    return db.query(Agent).order_by(Agent.name).all()


@router.get("/{agent_name}", response_model=AgentResponse)
def get_agent(agent_name: str, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.name == agent_name).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_name}", response_model=AgentResponse)
def update_agent(agent_name: str, body: AgentUpdate, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.name == agent_name).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.is_enabled = body.is_enabled
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/{agent_name}/tools", response_model=list[ToolConfigResponse])
def list_agent_tools(agent_name: str, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.name == agent_name).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return db.query(AgentToolConfig).filter(AgentToolConfig.agent_id == agent.id).order_by(AgentToolConfig.tool_name).all()


@router.patch("/{agent_name}/tools/{tool_name}", response_model=ToolConfigResponse)
def update_tool_config(agent_name: str, tool_name: str, body: ToolConfigUpdate, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.name == agent_name).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    config = db.query(AgentToolConfig).filter(
        AgentToolConfig.agent_id == agent.id,
        AgentToolConfig.tool_name == tool_name,
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail="Tool config not found")
    config.is_enabled = body.is_enabled
    db.commit()
    db.refresh(config)
    return config
