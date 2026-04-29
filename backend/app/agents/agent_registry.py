"""
Agent registry — single source of truth for all available agents.

To add a new agent:
1. Create agents/my_agent.py extending BaseITAgent
2. Add an instance to AGENT_REGISTRY below
"""
from app.agents.project_manager import ProjectManagerAgent
from app.agents.business_analyst import BusinessAnalystAgent
from app.agents.data_analyst import DataAnalystAgent
from app.agents.backend_developer import BackendDeveloperAgent
from app.agents.devops import DevOpsAgent
from app.agents.qa_engineer import QAEngineerAgent
from app.agents.support_engineer import SupportEngineerAgent

AGENT_REGISTRY: dict = {
    "ProjectManagerAgent": ProjectManagerAgent(),
    "BusinessAnalystAgent": BusinessAnalystAgent(),
    "DataAnalystAgent": DataAnalystAgent(),
    "BackendDeveloperAgent": BackendDeveloperAgent(),
    "DevOpsAgent": DevOpsAgent(),
    "QAEngineerAgent": QAEngineerAgent(),
    "SupportEngineerAgent": SupportEngineerAgent(),
}


def get_agent_descriptions(db=None) -> str:
    """Return a formatted string of agents and their capabilities for the orchestrator prompt.

    If db is provided, only enabled agents (per DB config) are included.
    """
    if db is not None:
        from app.models.agent import Agent as AgentModel
        enabled_rows = db.query(AgentModel).filter(AgentModel.is_enabled == True).all()  # noqa: E712
        enabled_names = {row.name for row in enabled_rows}
        agents_to_show = {
            name: agent for name, agent in AGENT_REGISTRY.items()
            if name in enabled_names
        }
    else:
        agents_to_show = AGENT_REGISTRY

    lines = []
    for name, agent in agents_to_show.items():
        lines.append(f"\n- {name}")
        lines.append(f"  Role: {agent.role}")
        lines.append(f"  Description: {agent.description}")
        caps = ", ".join(agent.capabilities)
        lines.append(f"  Capabilities: {caps}")
    return "\n".join(lines)
