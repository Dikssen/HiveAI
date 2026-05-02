"""
Base agent class. All IT-company agents extend BaseITAgent.
"""
from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseITAgent(ABC):
    """Abstract base for all IT-company agents."""

    name: str = "BaseAgent"
    role: str = "Generic Agent"
    goal: str = "Assist with tasks"
    backstory: str = "An AI assistant."
    description: str = "A generic AI agent."
    capabilities: list[str] = []

    @abstractmethod
    def get_tools(self) -> list[Any]:
        """Return all tools for this agent (unfiltered). Used for seeding and fallback."""
        ...

    def get_active_tools(self, db: Any) -> list[Any]:
        """Return only tools enabled in DB. Falls back to get_tools() if agent not seeded yet."""
        from app.models.agent import Agent
        from app.models.agent_tool_config import AgentToolConfig

        agent_row = db.query(Agent).filter(Agent.name == self.name).first()
        if not agent_row:
            return self.get_tools()

        disabled = {
            row.tool_name
            for row in db.query(AgentToolConfig).filter(
                AgentToolConfig.agent_id == agent_row.id,
                AgentToolConfig.is_enabled == False,  # noqa: E712
            ).all()
        }
        return [t for t in self.get_tools() if type(t).__name__ not in disabled]

    def describe(self) -> str:
        """Human-readable description for the orchestrator prompt."""
        caps = ", ".join(self.capabilities) if self.capabilities else "general tasks"
        return f"{self.name}: {self.description} | Capabilities: {caps}"
