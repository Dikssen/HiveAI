from abc import ABC, abstractmethod


class AgentRunner(ABC):
    @abstractmethod
    def run(
        self,
        agent_name: str,
        task_description: str,
        expected_output: str,
        supports_tools: bool,
    ) -> str:
        """Run agent with given task and return its output as a string."""
        ...
