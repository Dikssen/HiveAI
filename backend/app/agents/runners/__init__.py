from app.agents.runners.base import AgentRunner
from app.agents.runners.langgraph_runner import LangGraphRunner


def get_agent_runner() -> AgentRunner:
    return LangGraphRunner()
