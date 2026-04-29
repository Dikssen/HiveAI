"""
LangGraph-based orchestrator.

Mirrors the same plan→run→evaluate→synthesize loop as Orchestrator
but expressed as a LangGraph StateGraph, enabling future streaming,
checkpointing, and graph visualisation.

Select via: ORCHESTRATOR_RUNNER=langgraph in .env / config.
"""
from __future__ import annotations

from typing import TypedDict, Any, Optional

import structlog
from sqlalchemy.orm import Session

from app.agents.agent_registry import AGENT_REGISTRY
from app.config import settings
from app.models.message import Message
from app.orchestrator.base import BaseOrchestrator, OrchestratorResult
from app.orchestrator.orchestrator import Orchestrator, _detect_language

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------

class OrchestratorState(TypedDict):
    # ── fixed inputs ──────────────────────────────────────
    chat_id: int
    user_message: str
    task_id: int
    user_language: str
    chat_history: str
    orchestrator_run_id: int
    # ── planning output ───────────────────────────────────
    reasoning: str
    current_tasks: list[dict]
    # ── loop state ────────────────────────────────────────
    iteration: int
    all_outputs: list[dict]
    tasks_created_log: list[dict]
    errors: list[str]
    # ── result ────────────────────────────────────────────
    final_answer: str
    done: bool


# ---------------------------------------------------------------------------
# LangGraph orchestrator
# ---------------------------------------------------------------------------

class LangGraphOrchestrator(BaseOrchestrator):
    """
    Wraps the same orchestration logic as Orchestrator but drives the
    plan/run/evaluate/synthesize cycle through a LangGraph StateGraph.
    """

    def __init__(self, db: Session):
        # Delegate all LLM calls and DB helpers to the plain Orchestrator.
        self._impl = Orchestrator(db)
        self.db = db
        self._graph = self._build_graph()

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self):
        from langgraph.graph import StateGraph, END

        impl = self._impl  # captured in closures below

        # ── nodes ──────────────────────────────────────────────────────

        def plan(state: OrchestratorState) -> dict:
            decision = impl._make_decision(
                state["user_message"],
                state["chat_history"],
                state["orchestrator_run_id"],
                state["user_language"],
            )
            reasoning = decision.get("reasoning", "")
            task_defs = decision.get("tasks", [])

            errors = list(state["errors"])
            valid_tasks = []
            for td in task_defs:
                if td.get("agent", "") in AGENT_REGISTRY:
                    valid_tasks.append(td)
                else:
                    msg = f"Agent '{td.get('agent')}' not in registry — skipped"
                    impl._log(state["orchestrator_run_id"], "WARNING", msg)
                    errors.append(msg)

            if not valid_tasks:
                impl._log(state["orchestrator_run_id"], "WARNING", "No valid agents — falling back to ProjectManagerAgent")
                valid_tasks = [{
                    "agent": "ProjectManagerAgent",
                    "description": state["user_message"],
                    "expected_output": "A detailed, helpful response to the user's request",
                }]

            return {"reasoning": reasoning, "current_tasks": valid_tasks, "errors": errors}

        def run_agents(state: OrchestratorState) -> dict:
            iteration = state["iteration"]
            supports_tools = settings.LLM_SUPPORTS_TOOLS
            prior_context = impl._build_prior_context(state["all_outputs"])
            all_outputs = list(state["all_outputs"])
            tasks_created_log = list(state["tasks_created_log"])

            impl._log(state["orchestrator_run_id"], "INFO",
                      f"Agentic loop iteration {iteration}/{settings.MAX_ORCHESTRATOR_ITERATIONS}",
                      {"agents": [td["agent"] for td in state["current_tasks"]]})

            for td in state["current_tasks"]:
                agent_name = td["agent"]
                task_desc = td["description"]
                full_prompt = (
                    f"## Context from previous work\n\n{prior_context}\n\n"
                    f"## Your task\n\n{task_desc}"
                    if prior_context else task_desc
                )
                ar = impl._create_agent_run(
                    chat_id=state["chat_id"],
                    agent_name=agent_name,
                    task_description=f"[Iter {iteration}] {task_desc}",
                    input_payload={
                        "iteration": iteration,
                        "task": task_desc,
                        "prior_context": prior_context,
                        "full_prompt": full_prompt,
                    },
                    task_id=state["task_id"],
                    parent_run_id=state["orchestrator_run_id"],
                )
                impl._update_agent_run(ar, "running")

                output = impl._run_single_agent(
                    agent_name=agent_name,
                    task_description=task_desc,
                    expected_output=td.get("expected_output", "A detailed response"),
                    supports_tools=supports_tools,
                    prior_context=prior_context,
                )

                impl._update_agent_run(ar, "completed", output={"result": output, "iteration": iteration})
                impl._log(ar.id, "INFO", f"{agent_name} completed", {"preview": output[:200]})
                all_outputs.append({"agent": agent_name, "output": output, "iteration": iteration})
                tasks_created_log.append({"agent": agent_name, "description": td["description"], "status": "completed"})

            return {"all_outputs": all_outputs, "tasks_created_log": tasks_created_log}

        def evaluate(state: OrchestratorState) -> dict:
            iteration = state["iteration"]
            max_iter = settings.MAX_ORCHESTRATOR_ITERATIONS

            if iteration >= max_iter:
                impl._log(state["orchestrator_run_id"], "INFO", "Max iterations reached — stopping loop")
                return {"done": True}

            evaluation = impl._evaluate_result(
                state["user_message"], state["all_outputs"], state["orchestrator_run_id"]
            )

            if evaluation.get("is_complete", True):
                impl._log(state["orchestrator_run_id"], "INFO", "Evaluation: complete",
                          {"reason": evaluation.get("reason", "")[:200]})
                return {"done": True}

            next_agent = evaluation.get("next_agent", "")
            next_task = evaluation.get("next_task", {})

            if not next_agent or next_agent not in AGENT_REGISTRY:
                impl._log(state["orchestrator_run_id"], "WARNING",
                          f"Evaluation suggested unknown agent '{next_agent}' — stopping")
                return {"done": True}

            impl._log(state["orchestrator_run_id"], "INFO",
                      f"Evaluation: calling {next_agent} next",
                      {"reason": evaluation.get("reason", "")[:200]})

            return {
                "done": False,
                "current_tasks": [{"agent": next_agent, **next_task}],
                "iteration": iteration + 1,
            }

        def synthesize(state: OrchestratorState) -> dict:
            answer = impl._synthesize_answer(
                user_message=state["user_message"],
                all_outputs=state["all_outputs"],
                user_language=state["user_language"],
                run_id=state["orchestrator_run_id"],
            )
            return {"final_answer": answer}

        # ── routing ────────────────────────────────────────────────────

        def should_continue(state: OrchestratorState) -> str:
            return "synthesize" if state["done"] else "run_agents"

        # ── build graph ────────────────────────────────────────────────

        builder = StateGraph(OrchestratorState)
        builder.add_node("plan", plan)
        builder.add_node("run_agents", run_agents)
        builder.add_node("evaluate", evaluate)
        builder.add_node("synthesize", synthesize)

        builder.set_entry_point("plan")
        builder.add_edge("plan", "run_agents")
        builder.add_edge("run_agents", "evaluate")
        builder.add_conditional_edges("evaluate", should_continue, {
            "run_agents": "run_agents",
            "synthesize": "synthesize",
        })
        builder.add_edge("synthesize", END)

        return builder.compile()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, chat_id: int, user_message: str, task_id: int) -> OrchestratorResult:
        impl = self._impl
        errors: list[str] = []

        orchestrator_run = impl._create_agent_run(
            chat_id=chat_id,
            agent_name="ChiefOrchestratorAgent",
            task_description=f"Orchestrate: {user_message}",
            input_payload={"user_message": user_message, "task_id": task_id},
        )
        impl._update_agent_run(orchestrator_run, "running")

        try:
            user_language = _detect_language(user_message)
            chat_history = impl._get_chat_history(chat_id)

            initial_state: OrchestratorState = {
                "chat_id": chat_id,
                "user_message": user_message,
                "task_id": task_id,
                "user_language": user_language,
                "chat_history": chat_history,
                "orchestrator_run_id": orchestrator_run.id,
                "reasoning": "",
                "current_tasks": [],
                "iteration": 1,
                "all_outputs": [],
                "tasks_created_log": [],
                "errors": [],
                "final_answer": "",
                "done": False,
            }

            final_state = self._graph.invoke(initial_state)

            final_answer = final_state["final_answer"]
            all_outputs = final_state["all_outputs"]
            tasks_created_log = final_state["tasks_created_log"]
            reasoning = final_state["reasoning"]
            errors = final_state["errors"]

            self.db.add(Message(chat_id=chat_id, role="assistant", content=final_answer))
            self.db.commit()

            impl._update_agent_run(orchestrator_run, "completed", output={
                "reasoning": reasoning,
                "iterations": final_state["iteration"],
                "agents_used": [o["agent"] for o in all_outputs],
                "final_answer_preview": final_answer[:500],
            })
            impl._log(orchestrator_run.id, "INFO", "Orchestration completed (LangGraph)", {
                "total_iterations": final_state["iteration"],
                "agents": [o["agent"] for o in all_outputs],
            })

            return OrchestratorResult(
                reasoning=reasoning,
                selected_agents=list({o["agent"] for o in all_outputs}),
                tasks_created=tasks_created_log,
                final_answer=final_answer,
                agent_outputs=all_outputs,
                errors=errors,
            )

        except Exception as exc:
            error_msg = f"Orchestration failed: {exc}"
            logger.error(error_msg, exc_info=True)
            impl._update_agent_run(orchestrator_run, "failed", error=error_msg)

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
                errors=[error_msg],
            )
