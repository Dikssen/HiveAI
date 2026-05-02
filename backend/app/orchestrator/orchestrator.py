"""
ChiefOrchestrator — the decision-making brain of the IT company.

Flow:
  1. Receives user message and chat context
  2. LLM plans which agents to use and in what order (chain-of-thought)
  3. Unified agentic loop:
       a. Run the current agent, passing accumulated context from prior agents
       b. LLM evaluates: is the result complete?
       c. If not → LLM picks the next agent and task; loop continues
       d. Repeat up to MAX_ORCHESTRATOR_ITERATIONS (from config)
  4. LLM synthesizes a final answer in the user's language
  5. Saves result to DB
"""
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app.config import settings
from app.core.llm import get_langchain_llm
from app.agents.agent_registry import AGENT_REGISTRY, get_agent_descriptions
from app.agents.runners import get_agent_runner
from app.agents.runners.base import AgentRunner
from app.models.message import Message
from app.models.agent_run import AgentRun
from app.models.worker_log import WorkerLog
from app.orchestrator.base import BaseOrchestrator, OrchestratorResult

logger = structlog.get_logger()


def _detect_language(text: str) -> str:
    cyrillic = len(re.findall(r'[а-яА-ЯёЁіІїЇєЄґҐ]', text))
    latin = len(re.findall(r'[a-zA-Z]', text))
    if cyrillic > latin:
        ukrainian = len(re.findall(r'[іІїЇєЄґҐ]', text))
        return "Ukrainian" if ukrainian > 0 else "Russian"
    return "English"


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

ORCHESTRATOR_SYSTEM_PROMPT = """You are ChiefOrchestratorAgent — the lead AI orchestrator of an IT company.

You manage a team of specialized agents:{agent_descriptions}

Infrastructure knowledge base (agents can query it with KnowledgeSearch/KnowledgeGet):{knowledge_topics}

Think step by step before selecting agents (put this in "reasoning"):
  1. What exactly does the user need? List concrete sub-tasks.
  2. Can YOU answer directly — no agents needed?
  3. Which agent is best for each sub-task?
  4. In what order? Who depends on whom?
  5. Minimum agents — do not call an agent that adds no value.

DIRECT ANSWER (no agents) when:
  - Greeting, small talk, or a meta-question about the system
  - General knowledge requiring no tools, logs, code, or live data
  - Short clarification answerable from conversation history

AGENT TASKS when:
  - Files, logs, repos, Jira, Docker, or live data must be accessed
  - Code must be written, reviewed, or analyzed
  - A plan, estimate, or specification must be produced

LANGUAGE RULE: All task `description` fields must be in English.
If the user language is not English, each task description must end with:
"Your final response must be in {user_language}."

Return ONLY valid JSON — no markdown fences, no extra text.

Direct answer format:
{{
  "reasoning": "Why no agents are needed",
  "tasks": [],
  "direct_answer": "Full response in {user_language}"
}}

Agent tasks format:
{{
  "reasoning": "Step-by-step: what is needed, who does what, and why in this order",
  "tasks": [
    {{
      "agent": "AgentName",
      "description": "Precise task in English. Your final response must be in {user_language}.",
      "expected_output": "What this agent must produce"
    }}
  ]
}}

Rules:
- Each tasks[].agent MUST exactly match a name from the agent list above
- Prefer the smallest agent set — one agent is correct for simple requests
- Do not plan the same agent twice consecutively unless one writes code and the next reviews it
"""

EVALUATION_SYSTEM_PROMPT = """You are ChiefOrchestratorAgent reviewing the work done so far.

Available agents:{agent_descriptions}

Evaluate in this order — stop at the first rule that matches:

1. AGENT_FAILED — most recent output starts with "[AGENT_FAILED:":
   → NOT complete. Same agent, new instruction:
     "The previous attempt failed to execute tools. Do NOT output JSON blobs — run the tools and return actual results."

2. AGENT_TIMEOUT — most recent output starts with "[AGENT_TIMEOUT:":
   → NOT complete. Same agent, new instruction:
     "The previous attempt timed out. Narrow your approach — fewer tool calls, smaller search scope."

3. APPROVED — most recent output starts with "APPROVED:":
   → COMPLETE. The work is verified.

4. LOOP — same agent has produced substantially similar output twice in a row:
   → COMPLETE. Break the loop.

5. QUALITY CHECK — does the work genuinely answer the user's request?
   - Code was written but not yet reviewed → send to a QA/review agent (only once)
   - A review found issues not yet fixed → send to a developer/fix agent (only once)
   - After one write→review→fix cycle, mark COMPLETE regardless of remaining minor issues
   - All issues resolved or no issues found → COMPLETE

Return ONLY valid JSON — no markdown, no extra text.
If uncertain, return: {{"is_complete": true, "reason": "Unable to evaluate"}}

If complete:
{{
  "is_complete": true,
  "reason": "Concise explanation of why the work is done"
}}

If more work is needed:
{{
  "is_complete": false,
  "reason": "What is missing or wrong",
  "next_agent": "ExactAgentName",
  "next_task": {{
    "description": "Precise task in English — reference prior work explicitly",
    "expected_output": "What the agent must produce"
  }}
}}

Rules:
- Only mark complete if the output genuinely addresses the user's request
- next_agent MUST exactly match a name from the available agent list
- Do NOT repeat the same agent consecutively unless rules 1 or 2 above apply
"""

SYNTHESIS_SYSTEM_PROMPT = """You are ChiefOrchestratorAgent. Your team has finished working on a user request.
Synthesize all agent outputs into a single clear answer for the user.

Rules:
- Write in {user_language}
- Distill key findings, decisions, and results — do not repeat agents verbatim
- Preserve all code blocks exactly as produced — never paraphrase or shorten code
- If multiple iterations occurred (write → review → fix), present only the final approved state
- Use markdown where it improves readability: headers, bullet lists, code blocks
- Briefly mention remaining limitations or open questions at the end if any exist
"""


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator(BaseOrchestrator):
    def __init__(self, db: Session):
        self.db = db
        self._langchain_llm_json: Any = None
        self._langchain_llm_text: Any = None
        self._agent_runner: Optional[AgentRunner] = None

    def _langchain_json(self):
        if not self._langchain_llm_json:
            self._langchain_llm_json = get_langchain_llm(json_mode=True)
        return self._langchain_llm_json

    def _langchain_text(self):
        if not self._langchain_llm_text:
            self._langchain_llm_text = get_langchain_llm(json_mode=False)
        return self._langchain_llm_text

    def _runner(self) -> AgentRunner:
        if not self._agent_runner:
            self._agent_runner = get_agent_runner()
        return self._agent_runner

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _log(self, run_id: Optional[int], level: str, message: str, meta: Optional[dict] = None) -> None:
        entry = WorkerLog(
            agent_run_id=run_id,
            worker_name="ChiefOrchestrator",
            level=level,
            message=message,
            metadata_=meta or {},
        )
        self.db.add(entry)
        self.db.commit()
        getattr(logger, level.lower(), logger.info)(message, **(meta or {}))

    def _create_agent_run(
        self,
        chat_id: int,
        agent_name: str,
        task_description: str,
        input_payload: dict,
        task_id: Optional[int] = None,
        parent_run_id: Optional[int] = None,
    ) -> AgentRun:
        ar = AgentRun(
            chat_id=chat_id,
            agent_name=agent_name,
            task_description=task_description,
            status="pending",
            input_payload=input_payload,
            task_id=task_id,
            parent_run_id=parent_run_id,
        )
        self.db.add(ar)
        self.db.commit()
        self.db.refresh(ar)
        return ar

    def _update_agent_run(self, ar: AgentRun, status: str, output: Optional[dict] = None, error: Optional[str] = None) -> None:
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
        recent = messages[-10:] if len(messages) > 10 else messages
        return "\n".join(f"{m.role.upper()}: {m.content[:500]}" for m in recent)

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------

    def _parse_json(self, raw: str) -> dict:
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise ValueError(f"Cannot parse JSON from LLM response: {raw[:300]}")

    # ------------------------------------------------------------------
    # LLM: initial planning
    # ------------------------------------------------------------------

    def _make_decision(self, user_message: str, chat_history: str, run_id: int, user_language: str) -> dict:
        system = ORCHESTRATOR_SYSTEM_PROMPT.format(
            agent_descriptions=get_agent_descriptions(db=self.db),
            knowledge_topics=self._get_knowledge_topics(),
            user_language=user_language,
        )
        context = (
            f"Chat history:\n{chat_history}\n\nCurrent request: {user_message}"
            if chat_history else user_message
        )
        from app.models.agent import Agent as AgentModel
        enabled_names = [
            r.name for r in self.db.query(AgentModel).filter(AgentModel.is_enabled == True).all()  # noqa: E712
        ]
        self._log(run_id, "INFO", "Planning: selecting agents", {
            "user_message": user_message[:300],
            "available_agents": enabled_names,
        })
        response = self._langchain_json().invoke([SystemMessage(content=system), HumanMessage(content=context)])
        raw = response.content if hasattr(response, "content") else str(response)
        decision = self._parse_json(raw)
        self._log(run_id, "INFO", "Plan ready", {
            "selected_agents": [td["agent"] for td in decision.get("tasks", [])],
            "reasoning": decision.get("reasoning", "")[:300],
        })
        return decision

    # ------------------------------------------------------------------
    # LLM: evaluate result after each agent
    # ------------------------------------------------------------------

    def _evaluate_result(self, user_message: str, all_outputs: list[dict], run_id: int) -> dict:
        system = EVALUATION_SYSTEM_PROMPT.format(agent_descriptions=get_agent_descriptions(db=self.db))
        outputs_text = "\n\n".join(
            f"--- Iteration {o['iteration']} | {o['agent']} ---\n{o['output']}"
            for o in all_outputs[-5:]  # limit to last 5 to avoid context overflow
        )
        context = f"User request:\n{user_message}\n\nWork done so far:\n{outputs_text}"
        try:
            response = self._langchain_json().invoke([SystemMessage(content=system), HumanMessage(content=context)])
            raw = response.content if hasattr(response, "content") else str(response)
            evaluation = self._parse_json(raw)
        except Exception as exc:
            self._log(run_id, "WARNING", "Evaluation failed — assuming complete", {"error": str(exc)[:300]})
            evaluation = {"is_complete": True, "reason": f"Evaluation failed: {exc}"}
        self._log(run_id, "INFO", "Evaluation result", {
            "is_complete": evaluation.get("is_complete"),
            "reason": evaluation.get("reason", "")[:200],
            "next_agent": evaluation.get("next_agent"),
        })
        return evaluation

    # ------------------------------------------------------------------
    # LLM: synthesize final user-facing answer
    # ------------------------------------------------------------------

    def _synthesize_answer(self, user_message: str, all_outputs: list[dict], user_language: str, run_id: int) -> str:
        # Single agent — agent already responded in the correct language per task instructions
        if len(all_outputs) == 1:
            self._log(run_id, "INFO", "Synthesis skipped — single agent output")
            return all_outputs[0]["output"]

        system = SYNTHESIS_SYSTEM_PROMPT.format(user_language=user_language)
        outputs_text = "\n\n".join(
            f"--- Iteration {o['iteration']} | {o['agent']} ---\n{o['output']}"
            for o in all_outputs
        )
        context = f"User request:\n{user_message}\n\nAgent outputs:\n{outputs_text}"
        response = self._langchain_text().invoke([SystemMessage(content=system), HumanMessage(content=context)])
        answer = response.content if hasattr(response, "content") else str(response)
        self._log(run_id, "INFO", "Final answer synthesized", {"preview": answer[:200]})
        return answer

    # ------------------------------------------------------------------
    # Agent runner — injects accumulated context from prior agents
    # ------------------------------------------------------------------

    def _get_knowledge_topics(self) -> str:
        from app.models.knowledge_entry import KnowledgeEntry
        entries = self.db.query(KnowledgeEntry).order_by(KnowledgeEntry.agent_name, KnowledgeEntry.title).all()
        if not entries:
            return "\n  (no entries yet)"
        lines = []
        for e in entries:
            tags = f" [{e.tags}]" if e.tags else ""
            scope = f" ({e.agent_name})" if e.agent_name else " (global)"
            lines.append(f"\n  - {e.title}{tags}{scope}")
        return "".join(lines)

    def _error_hint(self) -> str:
        if settings.LLM_PROVIDER == "anthropic":
            return (
                f"- Перевірте Anthropic API ключ (LLM_API_KEY)\n"
                f"- Модель: {settings.LLM_MODEL}"
            )
        if settings.LLM_PROVIDER == "ollama":
            return (
                f"- Ollama запущена локально (`ollama serve`)\n"
                f"- Модель завантажена (`ollama pull {settings.LLM_MODEL}`)\n"
                f"- URL доступний: {settings.LLM_BASE_URL}"
            )
        return (
            f"- LLM endpoint: {settings.LLM_BASE_URL}\n"
            f"- Модель: {settings.LLM_MODEL}\n"
            f"- API ключ налаштовано (LLM_API_KEY)"
        )

    def _inject_language(self, tasks: list[dict], user_language: str) -> list[dict]:
        """Guarantee every task description ends with a language directive when not English."""
        if user_language == "English":
            return tasks
        suffix = f"\n\nYour final response must be in {user_language}."
        for td in tasks:
            desc = td.get("description", "")
            if f"in {user_language}" not in desc:
                td["description"] = desc + suffix
        return tasks

    def _is_agent_enabled(self, agent_name: str) -> bool:
        from app.models.agent import Agent
        row = self.db.query(Agent).filter(Agent.name == agent_name).first()
        return row.is_enabled if row else True

    def _build_prior_context(self, all_outputs: list[dict]) -> str:
        if not all_outputs:
            return ""
        parts = []
        for o in all_outputs[-3:]:  # pass last 3 complete outputs to avoid context overflow
            parts.append(f"### Iteration {o['iteration']} — {o['agent']}\n{o['output']}")
        return "\n\n".join(parts)

    def _is_unexecuted_action(self, output: str) -> bool:
        """
        Detect when the LLM returned a raw ReAct action blob instead of actual results.
        DeepSeek sometimes outputs {"Thought": ..., "Action": ..., "Action Input": ...}
        as its final answer without executing the tool.
        """
        text = output.strip().lstrip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                keys = {k.lower() for k in parsed.keys()}
                return bool(keys & {"action", "thought", "action_input"})
        except (json.JSONDecodeError, ValueError):
            pass
        return False

    def _run_single_agent(
        self,
        agent_name: str,
        task_description: str,
        expected_output: str,
        supports_tools: bool,
        prior_context: str = "",
    ) -> str:
        if prior_context:
            full_description = (
                f"## Context from previous work\n\n{prior_context}\n\n"
                f"## Your task\n\n{task_description}"
            )
        else:
            full_description = task_description

        output = self._runner().run(agent_name, full_description, expected_output, supports_tools, db=self.db)

        if self._is_unexecuted_action(output):
            logger.warning("Agent returned raw action JSON — tool was not executed", agent=agent_name, raw=output[:200])
            output = (
                f"[AGENT_FAILED: {agent_name} returned a raw tool-call JSON instead of executing the tool. "
                f"The agent intended to call: {output[:300]}\n"
                f"In the next iteration, explicitly execute the intended action and return the actual results.]"
            )

        return output

    # ------------------------------------------------------------------
    # Main run — unified agentic loop
    # ------------------------------------------------------------------

    def run(self, chat_id: int, user_message: str, task_id: int) -> OrchestratorResult:
        errors: list[str] = []
        all_outputs: list[dict] = []          # {"agent", "output", "iteration"}
        tasks_created_log: list[dict] = []
        active_runs: dict[str, AgentRun] = {}

        orchestrator_run = self._create_agent_run(
            chat_id=chat_id,
            agent_name="ChiefOrchestratorAgent",
            task_description=f"Orchestrate: {user_message}",
            input_payload={"user_message": user_message, "task_id": task_id},
            task_id=task_id,
        )
        self._update_agent_run(orchestrator_run, "running")

        try:
            user_language = _detect_language(user_message)
            chat_history = self._get_chat_history(chat_id)
            decision = self._make_decision(user_message, chat_history, orchestrator_run.id, user_language)

            reasoning = decision.get("reasoning", "")
            task_defs = decision.get("tasks", [])
            direct_answer = decision.get("direct_answer") or ""

            # Direct answer — no agents needed
            if direct_answer and not task_defs:
                self._log(orchestrator_run.id, "INFO", "direct_answer", {"preview": direct_answer[:200]})
                self.db.add(Message(chat_id=chat_id, role="assistant", content=direct_answer))
                self.db.commit()
                self._update_agent_run(orchestrator_run, "completed", output={
                    "reasoning": reasoning,
                    "direct_answer_preview": direct_answer[:500],
                })
                return OrchestratorResult(
                    reasoning=reasoning,
                    selected_agents=[],
                    tasks_created=[],
                    final_answer=direct_answer,
                    agent_outputs=[],
                    errors=[],
                )

            # Validate agents exist in registry and are enabled in DB
            valid_tasks = []
            for td in task_defs:
                agent_name = td.get("agent", "")
                if agent_name not in AGENT_REGISTRY:
                    msg = f"Agent '{agent_name}' not in registry — skipped"
                    self._log(orchestrator_run.id, "WARNING", msg)
                    errors.append(msg)
                elif not self._is_agent_enabled(agent_name):
                    msg = f"Agent '{agent_name}' is disabled in DB — skipped"
                    self._log(orchestrator_run.id, "WARNING", msg)
                    errors.append(msg)
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

            self._inject_language(valid_tasks, user_language)
            supports_tools = settings.LLM_SUPPORTS_TOOLS
            max_iter = settings.MAX_ORCHESTRATOR_ITERATIONS
            iteration = 1
            current_tasks = valid_tasks

            # ── Unified agentic loop ──────────────────────────────────
            while iteration <= max_iter:
                agent_names = [td["agent"] for td in current_tasks]
                self._log(orchestrator_run.id, "INFO", "loop_iteration", {
                    "iteration": iteration, "max": max_iter, "agents": agent_names,
                })

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

                    output = self._run_single_agent(
                        agent_name=agent_name,
                        task_description=task_desc,
                        expected_output=td.get("expected_output", "A detailed response"),
                        supports_tools=supports_tools,
                        prior_context=prior_context,
                    )

                    self._update_agent_run(ar, "completed", output={"result": output, "iteration": iteration})
                    all_outputs.append({"agent": agent_name, "output": output, "iteration": iteration})
                    tasks_created_log.append({"agent": agent_name, "description": td["description"], "status": "completed"})

                # Last iteration — skip evaluation, go straight to synthesis
                if iteration >= max_iter:
                    self._log(orchestrator_run.id, "INFO", "max_iterations_reached", {"iteration": iteration})
                    break

                # Evaluate: is the work done?
                evaluation = self._evaluate_result(user_message, all_outputs, orchestrator_run.id)

                if evaluation.get("is_complete", True):
                    self._log(orchestrator_run.id, "INFO", "evaluation_complete", {
                        "iteration": iteration,
                        "reason": evaluation.get("reason", "")[:200],
                    })
                    break

                # Not done — prepare next agent
                next_agent = evaluation.get("next_agent", "")
                next_task = evaluation.get("next_task", {})

                if not next_agent or next_agent not in AGENT_REGISTRY or not self._is_agent_enabled(next_agent):
                    self._log(orchestrator_run.id, "WARNING", "evaluation_unknown_agent", {
                        "next_agent": next_agent,
                    })
                    break

                self._log(orchestrator_run.id, "INFO", "evaluation_continue", {
                    "next_agent": next_agent,
                    "reason": evaluation.get("reason", "")[:200],
                })
                current_tasks = [{"agent": next_agent, **next_task}]
                self._inject_language(current_tasks, user_language)
                iteration += 1

            # ── Synthesize final answer ───────────────────────────────
            final_answer = self._synthesize_answer(
                user_message=user_message,
                all_outputs=all_outputs,
                user_language=user_language,
                run_id=orchestrator_run.id,
            )

            self.db.add(Message(chat_id=chat_id, role="assistant", content=final_answer))
            self.db.commit()

            self._update_agent_run(orchestrator_run, "completed", output={
                "reasoning": reasoning,
                "iterations": iteration,
                "agents_used": [o["agent"] for o in all_outputs],
                "final_answer_preview": final_answer[:500],
            })
            self._log(orchestrator_run.id, "INFO", "orchestration_done", {
                "iterations": iteration,
                "agents": [o["agent"] for o in all_outputs],
                "answer_chars": len(final_answer),
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
            errors.append(error_msg)

            self._update_agent_run(orchestrator_run, "failed", error=error_msg)
            for ar in active_runs.values():
                if ar.status == "running":
                    self._update_agent_run(ar, "failed", error=error_msg)

            error_reply = (
                f"❌ Помилка при обробці запиту:\n\n{error_msg}\n\n"
                f"Перевірте:\n{self._error_hint()}"
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
