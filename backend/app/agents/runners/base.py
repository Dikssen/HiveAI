from abc import ABC, abstractmethod
from typing import Any, Optional


class AgentRunner(ABC):
    @abstractmethod
    def run(
        self,
        agent_name: str,
        task_description: str,
        expected_output: str,
        supports_tools: bool,
        db: Optional[Any] = None,
    ) -> str:
        """Run agent with given task and return its output as a string."""
        ...
