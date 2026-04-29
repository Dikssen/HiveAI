"""
Base agent class. All IT-company agents extend BaseITAgent.
"""
from abc import ABC, abstractmethod
from typing import Any

from crewai import Agent as CrewAIAgent


class BaseITAgent(ABC):
    """
    Abstract base for all IT-company CrewAI agents.
    Subclasses define their role, capabilities, and tools.
    """

    name: str = "BaseAgent"
    role: str = "Generic Agent"
    goal: str = "Assist with tasks"
    backstory: str = "An AI assistant."
    description: str = "A generic AI agent."
    capabilities: list[str] = []

    @abstractmethod
    def get_tools(self) -> list[Any]:
        """Return list of CrewAI-compatible tool instances for this agent."""
        ...

    def get_crewai_agent(self, llm: Any, with_tools: bool = True) -> CrewAIAgent:
        """
        Build and return a configured CrewAI Agent.
        with_tools=False disables tools (useful when LLM doesn't support tool calling).
        """
        tools = self.get_tools() if with_tools else []
        return CrewAIAgent(
            role=self.role,
            goal=self.goal,
            backstory=self.backstory,
            tools=tools,
            llm=llm,
            verbose=True,
            allow_delegation=False,
            max_iter=5,
        )

    def describe(self) -> str:
        """Human-readable description for the orchestrator prompt."""
        caps = ", ".join(self.capabilities) if self.capabilities else "general tasks"
        return f"{self.name}: {self.description} | Capabilities: {caps}"
