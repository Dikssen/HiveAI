"""
ChiefOrchestrator — the decision-making brain of the IT company.

Flow:
  1. Receives user message and chat context
  2. Calls LLM (JSON mode) to decide which agents to use and what tasks to give them
  3. Creates AgentRun DB records for each selected agent
  4. Builds a CrewAI Crew with selected agents and their tasks
  5. Runs the Crew (sequential process)
  6. Saves results to DB and creates the assistant reply message
"""
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from crewai import Crew, Task as CrewTask, Process
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app.config import settings
from app.core.llm import get_crewai_llm, get_langchain_llm
from app.agents.agent_registry import AGENT_REGISTRY, get_agent_descriptions
from app.models.message import Message
from app.models.agent_run import AgentRun
from app.models.worker_log import WorkerLog

logger = structlog.get_logger()

# -------------------------------------------------------------------
# Orchestrator system prompt — tells the LLM how to select agents
# -------------------------------------------------------------------
ORCHESTRATOR_SYSTEM_PROMPT = """You are ChiefOrchestratorAgent — the lead AI orchestrator of an IT company.

You manage a team of specialized agents:{agent_descriptions}

Your job:
1. Analyze the user request (and chat history if provided)
2. Select the most appropriate agents for this request
3. Define a specific, actionable task for each selected agent
4. Return ONLY valid JSON — no markdown fences, no extra text

Required JSON format:
{{
  "reasoning": "Explain WHY you selected these agents and how they will collaborate to answer the request",
  "selected_agents": ["AgentName1", "AgentName2"],
  "tasks": [
    {{
      "agent": "AgentName1",
      "description": "Precise task description for this agent — what exactly should it do",
      "expected_output": "What this agent must produce (e.g., 'A markdown table of ticket counts by category')"
    }},
    {{
      "agent": "AgentName2",
      "description": "...",
      "expected_output": "..."
    }}
  ]
}}

Rules:
- Only include agents that are genuinely needed for this request
- Tasks should be ordered logically — later agents can build on earlier results
- Be specific: vague tasks produce poor outputs
- Use at most 3-4 agents unless the request truly requires more
- If the request is simple, one agent is fine
- Agent names MUST match exactly from the list above
"""


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


class Orchestrator:
    def __init__(self, db: Session):
        self.db = db
        self._langchain_llm = None
        self._crewai_llm = None

    def _langchain(self):
        if not self._langchain_llm:
            self._langchain_llm = get_langchain_llm(json_mode=True)
        return self._langchain_llm

    def _crewai(self):
        if not self._crewai_llm:
            self._crewai_llm = get_crewai_llm()
        return self._crewai_llm

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _log(
        self,
        agent_run_id: Optional[int],
        level: str,
        message: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Persist a log entry; also emit to structlog."""
        entry = WorkerLog(
            agent_run_id=agent_run_id,
            worker_name="ChiefOrchestrator",
            level=level,
            message=message,
            metadata_=metadata or {},
        )
        self.db.add(entry)
        self.db.commit()
        log_fn = getattr(logger, level.lower(), logger.info)
        log_fn(message, **(metadata or {}))

    def _create_agent_run(
        self,
        chat_id: int,
        agent_name: str,
        task_description: str,
        input_payload: dict,
    ) -> AgentRun:
        ar = AgentRun(
            chat_id=chat_id,
            agent_name=agent_name,
            task_description=task_description,
            status="pending",
            input_payload=input_payload,
        )
        self.db.add(ar)
        self.db.commit()
        self.db.refresh(ar)
        return ar

    def _update_agent_run(
        self,
        ar: AgentRun,
        status: str,
        output: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        ar.status = status
        if status == "running":
            ar.started_at = datetime.now(timezone.utc)
        elif status in ("completed", "failed"):
            ar.finished_at = datetime.now(timezone.utc)
        if output is not None:
            ar.output_payload = output
        if error is not None:
            ar.error = error
        self.db.commit()

    # ------------------------------------------------------------------
    # Chat history
    # ------------------------------------------------------------------

    def _get_chat_history(self, chat_id: int) -> str:
        messages = (
            self.db.query(Message)
            .filter(Message.chat_id == chat_id)
            .order_by(Message.created_at)
            .all()
        )
        # Keep last 10 messages for context window efficiency
        recent = messages[-10:] if len(messages) > 10 else messages
        return "\n".join(f"{m.role.upper()}: {m.content}" for m in recent)

    # ------------------------------------------------------------------
    # LLM decision: which agents to call
    # ------------------------------------------------------------------

    def _parse_json(self, raw: str) -> dict:
        """Robustly extract JSON from LLM output."""
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # Strip markdown fences if present
        raw_clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        try:
            return json.loads(raw_clean)
        except json.JSONDecodeError:
            pass
        # Extract first {...} block
        m = re.search(r"\{.*\}", raw_clean, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise ValueError(f"Cannot parse JSON from LLM response: {raw[:300]}")

    def _make_decision(
        self,
        user_message: str,
        chat_history: str,
        orchestrator_run_id: int,
    ) -> dict:
        agent_descriptions = get_agent_descriptions()
        system_prompt = ORCHESTRATOR_SYSTEM_PROMPT.format(
            agent_descriptions=agent_descriptions
        )
        context = (
            f"Chat history:\n{chat_history}\n\nCurrent request: {user_message}"
            if chat_history
            else user_message
        )

        self._log(
            orchestrator_run_id,
            "INFO",
            "Sending request to LLM for agent selection decision",
            {
                "user_message": user_message[:300],
                "available_agents": list(AGENT_REGISTRY.keys()),
            },
        )

        llm = self._langchain()
        response = llm.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=context)]
        )
        raw = response.content if hasattr(response, "content") else str(response)

        self._log(
            orchestrator_run_id,
            "DEBUG",
            "LLM decision received",
            {"raw_response_preview": raw[:500]},
        )

        decision = self._parse_json(raw)

        self._log(
            orchestrator_run_id,
            "INFO",
            "Orchestrator decision parsed successfully",
            {
                "selected_agents": decision.get("selected_agents", []),
                "reasoning": decision.get("reasoning", "")[:300],
                "num_tasks": len(decision.get("tasks", [])),
            },
        )
        return decision

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(self, chat_id: int, user_message: str, task_id: int) -> OrchestratorResult:
        errors: list[str] = []
        agent_outputs: list[dict] = []
        agent_run_map: dict[str, AgentRun] = {}  # initialized here so except block can access it

        # Create the orchestrator's own tracking record
        orchestrator_run = self._create_agent_run(
            chat_id=chat_id,
            agent_name="ChiefOrchestratorAgent",
            task_description=f"Orchestrate: {user_message[:120]}",
            input_payload={"user_message": user_message, "task_id": task_id},
        )
        self._update_agent_run(orchestrator_run, "running")

        try:
            chat_history = self._get_chat_history(chat_id)
            decision = self._make_decision(user_message, chat_history, orchestrator_run.id)

            reasoning = decision.get("reasoning", "")
            task_defs = decision.get("tasks", [])

            # Validate that selected agents exist in the registry
            valid_task_defs = []
            for td in task_defs:
                agent_name = td.get("agent", "")
                if agent_name in AGENT_REGISTRY:
                    valid_task_defs.append(td)
                else:
                    msg = f"Agent '{agent_name}' not found in registry — skipping"
                    self._log(orchestrator_run.id, "WARNING", msg)
                    errors.append(msg)

            # Fallback: always have at least one agent
            if not valid_task_defs:
                self._log(
                    orchestrator_run.id,
                    "WARNING",
                    "No valid agents in decision — falling back to ProjectManagerAgent",
                )
                valid_task_defs = [
                    {
                        "agent": "ProjectManagerAgent",
                        "description": user_message,
                        "expected_output": "A detailed, helpful response to the user's request",
                    }
                ]

            # Create AgentRun records before starting crew
            for td in valid_task_defs:
                agent_name = td["agent"]
                ar = self._create_agent_run(
                    chat_id=chat_id,
                    agent_name=agent_name,
                    task_description=td["description"],
                    input_payload={
                        "description": td["description"],
                        "expected_output": td.get("expected_output", ""),
                    },
                )
                agent_run_map[agent_name] = ar

            # Build CrewAI agents and tasks
            crewai_llm = self._crewai()
            supports_tools = settings.LLM_SUPPORTS_TOOLS

            crew_agents = []
            crew_tasks: list[CrewTask] = []

            for td in valid_task_defs:
                agent_name = td["agent"]
                agent_impl = AGENT_REGISTRY[agent_name]

                crewai_agent = agent_impl.get_crewai_agent(
                    llm=crewai_llm, with_tools=supports_tools
                )
                crew_agents.append(crewai_agent)

                # Pass completed tasks as context so agents can build on each other
                task_context = crew_tasks.copy() if crew_tasks else None
                crewai_task = CrewTask(
                    description=td["description"],
                    expected_output=td.get("expected_output", "A detailed response"),
                    agent=crewai_agent,
                    context=task_context,
                )
                crew_tasks.append(crewai_task)

                self._update_agent_run(agent_run_map[agent_name], "running")

            self._log(
                orchestrator_run.id,
                "INFO",
                "CrewAI crew starting",
                {
                    "agents": [td["agent"] for td in valid_task_defs],
                    "process": "sequential",
                },
            )

            # Run the crew
            crew = Crew(
                agents=crew_agents,
                tasks=crew_tasks,
                process=Process.sequential,
                verbose=True,
            )
            crew_result = crew.kickoff()

            # Collect per-task outputs and update DB records
            tasks_created_log = []
            for td, crew_task in zip(valid_task_defs, crew_tasks):
                agent_name = td["agent"]
                ar = agent_run_map[agent_name]

                # Extract output text from CrewAI task
                task_output_text = ""
                if hasattr(crew_task, "output") and crew_task.output is not None:
                    out = crew_task.output
                    task_output_text = (
                        out.raw if hasattr(out, "raw") else str(out)
                    )
                if not task_output_text:
                    task_output_text = str(crew_result) if crew_result else ""

                self._update_agent_run(
                    ar,
                    "completed",
                    output={"result": task_output_text[:8000]},
                )
                self._log(
                    ar.id,
                    "INFO",
                    f"Agent {agent_name} completed successfully",
                    {"output_preview": task_output_text[:300]},
                )

                agent_outputs.append(
                    {"agent": agent_name, "output": task_output_text, "status": "completed"}
                )
                tasks_created_log.append(
                    {
                        "agent": agent_name,
                        "description": td["description"],
                        "status": "completed",
                    }
                )

            # Final answer is the last crew task's output
            final_answer = str(crew_result) if crew_result else "Task completed."

            # Persist as assistant message
            self.db.add(
                Message(chat_id=chat_id, role="assistant", content=final_answer)
            )
            self.db.commit()

            self._update_agent_run(
                orchestrator_run,
                "completed",
                output={
                    "reasoning": reasoning,
                    "selected_agents": [td["agent"] for td in valid_task_defs],
                    "final_answer_preview": final_answer[:500],
                },
            )
            self._log(
                orchestrator_run.id,
                "INFO",
                "Orchestration completed",
                {
                    "agents_used": [td["agent"] for td in valid_task_defs],
                    "final_answer_preview": final_answer[:200],
                },
            )

            return OrchestratorResult(
                reasoning=reasoning,
                selected_agents=[td["agent"] for td in valid_task_defs],
                tasks_created=tasks_created_log,
                final_answer=final_answer,
                agent_outputs=agent_outputs,
                errors=errors,
            )

        except Exception as exc:
            error_msg = f"Orchestration failed: {exc}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)

            self._update_agent_run(orchestrator_run, "failed", error=error_msg)

            # Mark any still-running agent runs as failed
            for ar in agent_run_map.values():
                if ar.status == "running":
                    self._update_agent_run(ar, "failed", error=error_msg)

            # Persist error message so the user sees it in the chat
            error_reply = (
                f"❌ Помилка при обробці запиту:\n\n{error_msg}\n\n"
                "Перевірте:\n"
                "- Ollama запущена локально (`ollama serve`)\n"
                f"- Модель завантажена (`ollama pull {settings.LLM_MODEL}`)\n"
                f"- URL доступний: {settings.LLM_BASE_URL}"
            )
            self.db.add(Message(chat_id=chat_id, role="assistant", content=error_reply))
            self.db.commit()

            return OrchestratorResult(
                reasoning="Orchestration failed due to error",
                selected_agents=[],
                tasks_created=[],
                final_answer=error_reply,
                agent_outputs=[],
                errors=errors,
            )
