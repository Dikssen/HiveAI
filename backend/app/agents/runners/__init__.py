from app.agents.runners.base import AgentRunner
from app.config import settings


def get_agent_runner() -> AgentRunner:
    if settings.AGENT_RUNNER == "langgraph":
        from app.agents.runners.langgraph_runner import LangGraphRunner
        return LangGraphRunner()
    from app.agents.runners.crewai_runner import CrewAIRunner
    return CrewAIRunner()
