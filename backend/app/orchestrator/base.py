from abc import ABC, abstractmethod


class OrchestratorResult:
    def __init__(
        self,
        reasoning: str,
        selected_agents: list[str],
        tasks_created: list[dict],
        final_answer: str,
        agent_outputs: list[dict],
        errors: list[str],
    ):
        self.reasoning = reasoning
        self.selected_agents = selected_agents
        self.tasks_created = tasks_created
        self.final_answer = final_answer
        self.agent_outputs = agent_outputs
        self.errors = errors

    def to_dict(self) -> dict:
        return {
            "reasoning": self.reasoning,
            "selected_agents": self.selected_agents,
            "tasks_created": self.tasks_created,
            "final_answer": self.final_answer,
            "agent_outputs": self.agent_outputs,
            "errors": self.errors,
        }


class BaseOrchestrator(ABC):
    @abstractmethod
    def run(self, chat_id: int, user_message: str, task_id: int) -> OrchestratorResult:
        ...
