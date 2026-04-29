import time
from typing import Any

import structlog
from crewai import Crew, Task as CrewTask, Process

from app.agents.runners.base import AgentRunner
from app.agents.agent_registry import AGENT_REGISTRY
from app.core.llm import get_crewai_llm

logger = structlog.get_logger()


class CrewAIRunner(AgentRunner):
    def __init__(self):
        self._llm: Any = None

    def _get_llm(self) -> Any:
        if not self._llm:
            self._llm = get_crewai_llm()
        return self._llm

    def run(self, agent_name: str, task_description: str, expected_output: str, supports_tools: bool) -> str:
        llm = self._get_llm()
        agent_impl = AGENT_REGISTRY[agent_name]
        crewai_agent = agent_impl.get_crewai_agent(llm=llm, with_tools=supports_tools)
        crew_task = CrewTask(
            description=task_description,
            expected_output=expected_output,
            agent=crewai_agent,
        )
        crew = Crew(agents=[crewai_agent], tasks=[crew_task], process=Process.sequential, verbose=False)

        logger.info("agent_start", agent=agent_name, tools=supports_tools, task_preview=task_description[:120])
        t0 = time.monotonic()
        result = crew.kickoff()
        elapsed = round(time.monotonic() - t0, 2)

        output = ""
        if hasattr(crew_task, "output") and crew_task.output is not None:
            out = crew_task.output
            output = out.raw if hasattr(out, "raw") else str(out)
        if not output:
            output = str(result) if result else ""

        logger.info("agent_done", agent=agent_name, elapsed_s=elapsed, output_chars=len(output))
        return output
