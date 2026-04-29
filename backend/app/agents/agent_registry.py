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


def get_agent_descriptions() -> str:
    """Return a formatted string of all agents and their capabilities for the orchestrator prompt."""
    lines = []
    for name, agent in AGENT_REGISTRY.items():
        lines.append(f"\n- {name}")
        lines.append(f"  Role: {agent.role}")
        lines.append(f"  Description: {agent.description}")
        caps = ", ".join(agent.capabilities)
        lines.append(f"  Capabilities: {caps}")
    return "\n".join(lines)
