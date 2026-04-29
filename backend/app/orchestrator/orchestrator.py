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
from pathlib import Path
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

REVIEW_LOOP_AGENTS = {"BackendDeveloperAgent", "QAEngineerAgent"}
MAX_REVIEW_ITERATIONS = 3
REPORTS_ROOT = Path("/app/repos/reports")


def _detect_language(text: str) -> str:
    cyrillic = len(re.findall(r'[а-яА-ЯёЁіІїЇєЄґҐ]', text))
    latin = len(re.findall(r'[a-zA-Z]', text))
    if cyrillic > latin:
        ukrainian = len(re.findall(r'[іІїЇєЄґҐ]', text))
        return "Ukrainian" if ukrainian > 0 else "Russian"
    return "English"


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
- All task descriptions for agents MUST be written in English
- The final answer to the user must be in: {user_language}
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
        user_language: str = "English",
    ) -> dict:
        agent_descriptions = get_agent_descriptions()
        system_prompt = ORCHESTRATOR_SYSTEM_PROMPT.format(
            agent_descriptions=agent_descriptions,
            user_language=user_language,
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
    # Single-agent runner (helper for review loop)
    # ------------------------------------------------------------------

    def _run_single_agent(
        self,
        agent_name: str,
        task_description: str,
        expected_output: str,
        crewai_llm: Any,
        supports_tools: bool,
    ) -> str:
        agent_impl = AGENT_REGISTRY[agent_name]
        crewai_agent = agent_impl.get_crewai_agent(llm=crewai_llm, with_tools=supports_tools)
        crew_task = CrewTask(
            description=task_description,
            expected_output=expected_output,
            agent=crewai_agent,
        )
        crew = Crew(
            agents=[crewai_agent],
            tasks=[crew_task],
            process=Process.sequential,
            verbose=True,
        )
        result = crew.kickoff()
        if hasattr(crew_task, "output") and crew_task.output is not None:
            out = crew_task.output
            return out.raw if hasattr(out, "raw") else str(out)
        return str(result) if result else ""

    # ------------------------------------------------------------------
    # Review loop: Backend → QA → Backend... until QA approves
    # ------------------------------------------------------------------

    def _run_review_loop(
        self,
        chat_id: int,
        backend_td: dict,
        qa_td: dict,
        crewai_llm: Any,
        supports_tools: bool,
        orchestrator_run_id: int,
        agent_outputs: list,
        tasks_created_log: list,
        user_language: str = "English",
    ) -> str:
        report_dir = REPORTS_ROOT / f"chat_{chat_id}"
        report_dir.mkdir(parents=True, exist_ok=True)

        qa_feedback = ""
        final_output = ""

        for iteration in range(1, MAX_REVIEW_ITERATIONS + 1):
            self._log(
                orchestrator_run_id, "INFO",
                f"Review loop iteration {iteration}/{MAX_REVIEW_ITERATIONS}",
            )

            # --- BackendDeveloperAgent ---
            if qa_feedback:
                backend_desc = (
                    f"{backend_td['description']}\n\n"
                    f"### QA Feedback from Iteration {iteration - 1}\n"
                    f"{qa_feedback}\n\n"
                    f"Address all QA findings above and improve the solution."
                )
            else:
                backend_desc = backend_td["description"]

            backend_ar = self._create_agent_run(
                chat_id=chat_id,
                agent_name="BackendDeveloperAgent",
                task_description=f"[Iteration {iteration}] {backend_desc[:120]}",
                input_payload={"iteration": iteration, "description": backend_desc},
            )
            self._update_agent_run(backend_ar, "running")

            backend_output = self._run_single_agent(
                "BackendDeveloperAgent",
                backend_desc,
                backend_td.get("expected_output", "Analysis and proposed code fixes"),
                crewai_llm,
                supports_tools,
            )

            report_path = report_dir / f"iteration_{iteration}_backend.md"
            report_path.write_text(backend_output)

            self._update_agent_run(
                backend_ar, "completed",
                output={"result": backend_output[:8000], "iteration": iteration, "report": str(report_path)},
            )
            agent_outputs.append({"agent": "BackendDeveloperAgent", "output": backend_output, "status": "completed", "iteration": iteration})
            tasks_created_log.append({"agent": "BackendDeveloperAgent", "description": f"Iteration {iteration}", "status": "completed"})

            # --- QAEngineerAgent ---
            qa_desc = (
                f"{qa_td['description']}\n\n"
                f"### Backend Developer's Work — Iteration {iteration}\n"
                f"{backend_output[:5000]}\n\n"
                f"If the implementation is complete and correct, start your response with 'APPROVED: '.\n"
                f"Otherwise list the specific issues that still need to be fixed.\n\n"
                f"IMPORTANT: Write your final response in {user_language}."
            )

            qa_ar = self._create_agent_run(
                chat_id=chat_id,
                agent_name="QAEngineerAgent",
                task_description=f"[Iteration {iteration}] Review Backend work",
                input_payload={"iteration": iteration, "description": qa_desc},
            )
            self._update_agent_run(qa_ar, "running")

            qa_output = self._run_single_agent(
                "QAEngineerAgent",
                qa_desc,
                qa_td.get("expected_output", "QA review with approval or list of remaining issues"),
                crewai_llm,
                supports_tools,
            )

            qa_report_path = report_dir / f"iteration_{iteration}_qa.md"
            qa_report_path.write_text(qa_output)

            is_approved = qa_output.strip().upper().startswith("APPROVED")
            self._update_agent_run(
                qa_ar, "completed",
                output={"result": qa_output[:8000], "iteration": iteration, "approved": is_approved},
            )
            self._log(
                orchestrator_run_id, "INFO",
                f"Iteration {iteration} QA result",
                {"approved": is_approved, "preview": qa_output[:200]},
            )

            agent_outputs.append({"agent": "QAEngineerAgent", "output": qa_output, "status": "completed", "iteration": iteration})
            tasks_created_log.append({"agent": "QAEngineerAgent", "description": f"Iteration {iteration} review", "status": "completed"})

            qa_feedback = qa_output
            final_output = qa_output

            if is_approved:
                self._log(orchestrator_run_id, "INFO", f"QA approved on iteration {iteration}")
                break

        return final_output

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
            user_language = _detect_language(user_message)
            chat_history = self._get_chat_history(chat_id)
            decision = self._make_decision(user_message, chat_history, orchestrator_run.id, user_language)

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

            crewai_llm = self._crewai()
            supports_tools = settings.LLM_SUPPORTS_TOOLS
            tasks_created_log = []

            # Detect whether review loop is needed
            selected_names = {td["agent"] for td in valid_task_defs}
            use_review_loop = REVIEW_LOOP_AGENTS.issubset(selected_names)

            if use_review_loop:
                backend_td = next(td for td in valid_task_defs if td["agent"] == "BackendDeveloperAgent")
                qa_td = next(td for td in valid_task_defs if td["agent"] == "QAEngineerAgent")
                other_tds = [td for td in valid_task_defs if td["agent"] not in REVIEW_LOOP_AGENTS]

                self._log(orchestrator_run.id, "INFO", "Starting review loop", {"max_iterations": MAX_REVIEW_ITERATIONS})

                # Run any other agents (e.g. ProjectManager) with standard sequential crew first
                if other_tds:
                    for td in other_tds:
                        ar = self._create_agent_run(
                            chat_id=chat_id,
                            agent_name=td["agent"],
                            task_description=td["description"],
                            input_payload={"description": td["description"]},
                        )
                        agent_run_map[td["agent"]] = ar
                        self._update_agent_run(ar, "running")
                        out = self._run_single_agent(
                            td["agent"], td["description"],
                            td.get("expected_output", "A detailed response"),
                            crewai_llm, supports_tools,
                        )
                        self._update_agent_run(ar, "completed", output={"result": out[:8000]})
                        agent_outputs.append({"agent": td["agent"], "output": out, "status": "completed"})
                        tasks_created_log.append({"agent": td["agent"], "description": td["description"], "status": "completed"})

                final_answer = self._run_review_loop(
                    chat_id=chat_id,
                    backend_td=backend_td,
                    qa_td=qa_td,
                    crewai_llm=crewai_llm,
                    supports_tools=supports_tools,
                    orchestrator_run_id=orchestrator_run.id,
                    agent_outputs=agent_outputs,
                    tasks_created_log=tasks_created_log,
                    user_language=user_language,
                )

            else:
                # Standard sequential crew
                for td in valid_task_defs:
                    agent_name = td["agent"]
                    ar = self._create_agent_run(
                        chat_id=chat_id,
                        agent_name=agent_name,
                        task_description=td["description"],
                        input_payload={"description": td["description"], "expected_output": td.get("expected_output", "")},
                    )
                    agent_run_map[agent_name] = ar

                crew_agents = []
                crew_tasks: list[CrewTask] = []
                last_idx = len(valid_task_defs) - 1
                for i, td in enumerate(valid_task_defs):
                    agent_name = td["agent"]
                    crewai_agent = AGENT_REGISTRY[agent_name].get_crewai_agent(llm=crewai_llm, with_tools=supports_tools)
                    crew_agents.append(crewai_agent)
                    task_context = crew_tasks.copy() if crew_tasks else None
                    desc = td["description"]
                    if i == last_idx and user_language != "English":
                        desc += f"\n\nIMPORTANT: Write your final response in {user_language}."
                    crew_tasks.append(CrewTask(
                        description=desc,
                        expected_output=td.get("expected_output", "A detailed response"),
                        agent=crewai_agent,
                        context=task_context,
                    ))
                    self._update_agent_run(agent_run_map[agent_name], "running")

                self._log(orchestrator_run.id, "INFO", "CrewAI crew starting", {"agents": [td["agent"] for td in valid_task_defs]})

                crew_result = Crew(agents=crew_agents, tasks=crew_tasks, process=Process.sequential, verbose=True).kickoff()

                for td, crew_task in zip(valid_task_defs, crew_tasks):
                    agent_name = td["agent"]
                    ar = agent_run_map[agent_name]
                    task_output_text = ""
                    if hasattr(crew_task, "output") and crew_task.output is not None:
                        out = crew_task.output
                        task_output_text = out.raw if hasattr(out, "raw") else str(out)
                    if not task_output_text:
                        task_output_text = str(crew_result) if crew_result else ""
                    self._update_agent_run(ar, "completed", output={"result": task_output_text[:8000]})
                    self._log(ar.id, "INFO", f"Agent {agent_name} completed successfully", {"output_preview": task_output_text[:300]})
                    agent_outputs.append({"agent": agent_name, "output": task_output_text, "status": "completed"})
                    tasks_created_log.append({"agent": agent_name, "description": td["description"], "status": "completed"})

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
