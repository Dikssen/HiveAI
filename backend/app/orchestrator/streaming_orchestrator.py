"""
StreamingOrchestrator — streams SSE events during orchestration.

Progress events (planning, agent_start/complete, evaluating) are yielded
immediately. The final synthesis streams tokens via LLM.astream(),
giving ChatGPT-style character-by-character output.

SSE event shapes:
  {"type": "step",  "event": "planning"}
  {"type": "step",  "event": "decision", "agents": [...]}
  {"type": "step",  "event": "agent_start",    "agent": "...", "iteration": N}
  {"type": "step",  "event": "agent_complete", "agent": "...", "iteration": N}
  {"type": "step",  "event": "evaluating"}
  {"type": "step",  "event": "synthesizing"}
  {"type": "token", "content": "..."}          # one or more per synthesis
  {"type": "done",  "message_id": N}
  {"type": "error", "message": "...", "message_id": N}
"""
import asyncio
import json
from typing import AsyncGenerator

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.core.llm import get_langchain_llm
from app.agents.agent_registry import AGENT_REGISTRY
from app.models.message import Message
from app.orchestrator.orchestrator import (
    Orchestrator,
    _detect_language,
    SYNTHESIS_SYSTEM_PROMPT,
)

logger = structlog.get_logger()


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


class StreamingOrchestrator(Orchestrator):
    async def _run_agent_async(
        self,
        agent_name: str,
        task_desc: str,
        expected_output: str,
        supports_tools: bool,
        prior_context: str,
    ) -> str:
        """Run a synchronous CrewAI agent in a thread pool.

        Creates its own DB session to avoid SQLAlchemy thread-affinity issues.
        """
        from app.db.session import SessionLocal

        def _sync() -> str:
            thread_db = SessionLocal()
            try:
                full_description = (
                    f"## Context from previous work\n\n{prior_context}\n\n"
                    f"## Your task\n\n{task_desc}"
                    if prior_context
                    else task_desc
                )
                return self._runner().run(
                    agent_name,
                    full_description,
                    expected_output,
                    supports_tools,
                    db=thread_db,
                )
            finally:
                thread_db.close()

        output = await asyncio.to_thread(_sync)

        if self._is_unexecuted_action(output):
            logger.warning("agent_returned_raw_action_json", agent=agent_name, raw=output[:200])
            output = (
                f"[AGENT_FAILED: {agent_name} returned a raw tool-call JSON instead of "
                f"executing the tool. The agent intended to call: {output[:300]}\n"
                "In the next iteration, explicitly execute the intended action and return "
                "the actual results.]"
            )

        return output

    async def stream(
        self, chat_id: int, user_message: str, task_id: int
    ) -> AsyncGenerator[str, None]:
        errors: list[str] = []
        all_outputs: list[dict] = []
        tasks_created_log: list[dict] = []
        active_runs: dict = {}

        orchestrator_run = self._create_agent_run(
            chat_id=chat_id,
            agent_name="ChiefOrchestratorAgent",
            task_description=f"Orchestrate: {user_message}",
            input_payload={"user_message": user_message, "task_id": task_id},
            task_id=task_id,
        )
        self._update_agent_run(orchestrator_run, "running")

        try:
            yield _sse({"type": "step", "event": "planning"})

            user_language = _detect_language(user_message)
            chat_history = self._get_chat_history(chat_id)

            decision = await asyncio.to_thread(
                self._make_decision,
                user_message,
                chat_history,
                orchestrator_run.id,
                user_language,
            )

            reasoning = decision.get("reasoning", "")
            task_defs = decision.get("tasks", [])
            direct_answer = decision.get("direct_answer") or ""

            yield _sse({
                "type": "step",
                "event": "decision",
                "agents": decision.get("selected_agents", []),
            })

            # Direct answer — stream it immediately, no agents needed
            if direct_answer and not task_defs:
                self._log(orchestrator_run.id, "INFO", "direct_answer", {"preview": direct_answer[:200]})
                yield _sse({"type": "token", "content": direct_answer})

                msg = Message(chat_id=chat_id, role="assistant", content=direct_answer)
                self.db.add(msg)
                self.db.commit()
                self.db.refresh(msg)

                self._update_agent_run(orchestrator_run, "completed", output={
                    "reasoning": reasoning,
                    "direct_answer_preview": direct_answer[:500],
                })
                yield _sse({"type": "done", "message_id": msg.id})
                return

            valid_tasks = []
            for td in task_defs:
                agent_name = td.get("agent", "")
                if agent_name not in AGENT_REGISTRY:
                    errors.append(f"Agent '{agent_name}' not in registry — skipped")
                elif not self._is_agent_enabled(agent_name):
                    errors.append(f"Agent '{agent_name}' is disabled — skipped")
                else:
                    valid_tasks.append(td)

            if not valid_tasks:
                fallback = "ProjectManagerAgent"
                if self._is_agent_enabled(fallback):
                    self._log(orchestrator_run.id, "WARNING", "No valid agents — falling back to ProjectManagerAgent")
                    valid_tasks = [{
                        "agent": fallback,
                        "description": user_message,
                        "expected_output": "A detailed, helpful response to the user's request",
                    }]
                else:
                    raise RuntimeError("No enabled agents available to handle the request")

            supports_tools = settings.LLM_SUPPORTS_TOOLS
            max_iter = settings.MAX_ORCHESTRATOR_ITERATIONS
            iteration = 1
            current_tasks = valid_tasks

            while iteration <= max_iter:
                prior_context = self._build_prior_context(all_outputs)

                for td in current_tasks:
                    agent_name = td["agent"]
                    task_desc = td["description"]

                    ar = self._create_agent_run(
                        chat_id=chat_id,
                        agent_name=agent_name,
                        task_description=f"[Iter {iteration}] {task_desc}",
                        input_payload={
                            "iteration": iteration,
                            "task": task_desc,
                            "prior_context": prior_context,
                        },
                        task_id=task_id,
                        parent_run_id=orchestrator_run.id,
                    )
                    active_runs[agent_name] = ar
                    self._update_agent_run(ar, "running")

                    yield _sse({
                        "type": "step",
                        "event": "agent_start",
                        "agent": agent_name,
                        "iteration": iteration,
                    })

                    output = await self._run_agent_async(
                        agent_name,
                        task_desc,
                        td.get("expected_output", "A detailed response"),
                        supports_tools,
                        prior_context,
                    )

                    self._update_agent_run(ar, "completed", output={"result": output, "iteration": iteration})
                    all_outputs.append({"agent": agent_name, "output": output, "iteration": iteration})
                    tasks_created_log.append({"agent": agent_name, "description": task_desc, "status": "completed"})

                    yield _sse({
                        "type": "step",
                        "event": "agent_complete",
                        "agent": agent_name,
                        "iteration": iteration,
                    })

                if iteration >= max_iter:
                    self._log(orchestrator_run.id, "INFO", "max_iterations_reached", {"iteration": iteration})
                    break

                yield _sse({"type": "step", "event": "evaluating"})

                evaluation = await asyncio.to_thread(
                    self._evaluate_result, user_message, all_outputs, orchestrator_run.id
                )

                if evaluation.get("is_complete", True):
                    self._log(orchestrator_run.id, "INFO", "evaluation_complete", {
                        "iteration": iteration,
                        "reason": evaluation.get("reason", "")[:200],
                    })
                    break

                next_agent = evaluation.get("next_agent", "")
                next_task = evaluation.get("next_task", {})

                if not next_agent or next_agent not in AGENT_REGISTRY or not self._is_agent_enabled(next_agent):
                    self._log(orchestrator_run.id, "WARNING", "evaluation_unknown_agent", {"next_agent": next_agent})
                    break

                self._log(orchestrator_run.id, "INFO", "evaluation_continue", {
                    "next_agent": next_agent,
                    "reason": evaluation.get("reason", "")[:200],
                })
                current_tasks = [{"agent": next_agent, **next_task}]
                iteration += 1

            # ── Stream final synthesis ────────────────────────────────────
            yield _sse({"type": "step", "event": "synthesizing"})
            final_answer_parts: list[str] = []

            if len(all_outputs) == 1 and user_language == "English":
                # Single agent + English: skip synthesis LLM call, yield output directly
                content = all_outputs[0]["output"]
                final_answer_parts.append(content)
                yield _sse({"type": "token", "content": content})
            else:
                system = SYNTHESIS_SYSTEM_PROMPT.format(user_language=user_language)
                outputs_text = "\n\n".join(
                    f"--- Iteration {o['iteration']} | {o['agent']} ---\n{o['output']}"
                    for o in all_outputs
                )
                context = f"User request:\n{user_message}\n\nAgent outputs:\n{outputs_text}"

                llm = get_langchain_llm(json_mode=False)
                async for chunk in llm.astream([SystemMessage(content=system), HumanMessage(content=context)]):
                    token = chunk.content if hasattr(chunk, "content") else ""
                    if token:
                        final_answer_parts.append(token)
                        yield _sse({"type": "token", "content": token})

            final_answer = "".join(final_answer_parts)

            msg = Message(chat_id=chat_id, role="assistant", content=final_answer)
            self.db.add(msg)
            self.db.commit()
            self.db.refresh(msg)

            self._update_agent_run(orchestrator_run, "completed", output={
                "reasoning": reasoning,
                "iterations": iteration,
                "agents_used": [o["agent"] for o in all_outputs],
                "final_answer_preview": final_answer[:500],
            })
            self._log(orchestrator_run.id, "INFO", "streaming_orchestration_done", {
                "iterations": iteration,
                "agents": [o["agent"] for o in all_outputs],
                "answer_chars": len(final_answer),
            })

            yield _sse({"type": "done", "message_id": msg.id})

        except Exception as exc:
            error_msg = f"Streaming orchestration failed: {exc}"
            logger.error(error_msg, exc_info=True)

            self._update_agent_run(orchestrator_run, "failed", error=error_msg)
            for ar in active_runs.values():
                if ar.status == "running":
                    self._update_agent_run(ar, "failed", error=error_msg)

            error_reply = (
                f"❌ Помилка при обробці запиту:\n\n{error_msg}\n\n"
                "Перевірте:\n"
                "- Ollama запущена локально (`ollama serve`)\n"
                f"- Модель завантажена (`ollama pull {settings.LLM_MODEL}`)\n"
                f"- URL доступний: {settings.LLM_BASE_URL}"
            )
            msg = Message(chat_id=chat_id, role="assistant", content=error_reply)
            self.db.add(msg)
            self.db.commit()
            self.db.refresh(msg)

            yield _sse({"type": "error", "message": error_msg, "message_id": msg.id})


class StreamingLangGraphOrchestrator(StreamingOrchestrator):
    """
    LangGraph variant of the streaming orchestrator.

    - .stream()  → inherited from StreamingOrchestrator (async SSE events + token streaming)
    - .run()     → uses LangGraph StateGraph execution (same as LangGraphOrchestrator)

    This means ORCHESTRATOR_RUNNER=langgraph gets the same streaming UX while
    still routing non-streaming (Celery) runs through the LangGraph graph engine.
    When LangGraph's astream_events() support is added, it can be implemented here.
    """

    def __init__(self, db):
        super().__init__(db)
        from app.orchestrator.graph import LangGraphOrchestrator
        self._lg = LangGraphOrchestrator(db)

    def run(self, chat_id: int, user_message: str, task_id: int):
        return self._lg.run(chat_id, user_message, task_id)
