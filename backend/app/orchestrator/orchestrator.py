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

Before selecting agents, think step by step (put this in "reasoning"):
  1. What exactly does the user need? Break it into concrete sub-tasks.
  2. Which agent is best suited for each sub-task?
  3. In what order should they work? (who depends on whom?)
  4. What is the minimal set — avoid calling agents that add no value.

Return ONLY valid JSON — no markdown fences, no extra text:

{{
  "reasoning": "Step-by-step analysis: what is needed, who does what, and why in this order",
  "selected_agents": ["AgentName1", "AgentName2"],
  "tasks": [
    {{
      "agent": "AgentName1",
      "description": "Precise task description — what exactly should this agent do",
      "expected_output": "Concrete description of what this agent must produce"
    }},
    {{
      "agent": "AgentName2",
      "description": "...",
      "expected_output": "..."
    }}
  ]
}}

Rules:
- Agent names MUST match exactly from the list above
- All task descriptions MUST be in English
- Use at most 3-4 agents unless the request truly requires more
- One agent is fine for simple requests
- The final answer to the user must be in: {user_language}
- File modification rule: if the task requires creating or modifying files in a repository,
  the task description MUST end with this exact sentence:
  "After writing the code, call WriteLocalFile to save every changed file to disk.
   The confirmation 'Written X bytes to' MUST appear in your output — otherwise the task is not done."
"""

EVALUATION_SYSTEM_PROMPT = """You are ChiefOrchestratorAgent reviewing the work done so far.

Available agents:{agent_descriptions}

You receive the original user request and the log of all agent work done so far.
Decide whether the user's request is fully and correctly addressed.

Common patterns to watch for:
- If BackendDeveloperAgent wrote code → QAEngineerAgent should review it (if not done yet)
- If QAEngineerAgent found bugs → BackendDeveloperAgent should fix them (if not done yet)
- If the last agent already fixed all issues and QA approved → mark complete
- If the same agent tried the same thing twice without improvement → mark complete (avoid infinite loops)

AGENT FAILURE DETECTION — check for this first:
- If the output starts with "[AGENT_FAILED:" the agent returned a raw JSON tool call without executing it.
- Always mark as NOT complete. Set next_agent to the same agent and instruct it:
  "The previous iteration failed to execute tools. Do NOT output JSON action blobs — actually run the tools and return their results."

FILE WRITE VERIFICATION — apply this check whenever the request involves modifying or creating files:
- Look for ANY of these patterns in the agent output (they all mean WriteLocalFile was called):
    • "Written N bytes to"  (exact tool return string)
    • "written … bytes"     (paraphrase with a number and "bytes")
    • "written to … repository"
    • "saved … to disk"
    • "file written"
- If NONE of those patterns appear and the task required file changes, the files were NOT saved to disk.
- In that case mark as NOT complete, set next_agent to the same agent, and instruct it:
  "The previous iteration produced code but did NOT call WriteLocalFile.
   Read the code from the previous context and call WriteLocalFile now to save each file."
- If ANY of those patterns appear, treat file writing as confirmed — do NOT request another write.

Return ONLY valid JSON — no markdown fences, no extra text:

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
    "description": "Precise task in English — reference the prior work explicitly",
    "expected_output": "What the agent must produce"
  }}
}}

Rules:
- Only mark complete if the output genuinely answers the user's request
- Agent name MUST match exactly from the available list
- Be decisive — do not suggest the same agent twice in a row unless there is a clear new instruction
"""

SYNTHESIS_SYSTEM_PROMPT = """You are ChiefOrchestratorAgent. Your team has finished working on a user request.
Synthesize all agent outputs into a single clear answer for the user.

Rules:
- Write in {user_language}
- Distill the key findings, decisions, and results — do not repeat agents verbatim
- Include code if it was produced
- If there were multiple iterations (e.g. Backend + QA reviews), summarize the final approved state
- Mention any remaining limitations briefly
- Be concise but complete
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

    def _create_agent_run(self, chat_id: int, agent_name: str, task_description: str, input_payload: dict) -> AgentRun:
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
        return "\n".join(f"{m.role.upper()}: {m.content}" for m in recent)

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
            agent_descriptions=get_agent_descriptions(),
            user_language=user_language,
        )
        context = (
            f"Chat history:\n{chat_history}\n\nCurrent request: {user_message}"
            if chat_history else user_message
        )
        self._log(run_id, "INFO", "Planning: selecting agents", {
            "user_message": user_message[:300],
            "available_agents": list(AGENT_REGISTRY.keys()),
        })
        response = self._langchain_json().invoke([SystemMessage(content=system), HumanMessage(content=context)])
        raw = response.content if hasattr(response, "content") else str(response)
        decision = self._parse_json(raw)
        self._log(run_id, "INFO", "Plan ready", {
            "selected_agents": decision.get("selected_agents", []),
            "reasoning": decision.get("reasoning", "")[:300],
        })
        return decision

    # ------------------------------------------------------------------
    # LLM: evaluate result after each agent
    # ------------------------------------------------------------------

    def _evaluate_result(self, user_message: str, all_outputs: list[dict], run_id: int) -> dict:
        system = EVALUATION_SYSTEM_PROMPT.format(agent_descriptions=get_agent_descriptions())
        outputs_text = "\n\n".join(
            f"--- Iteration {o['iteration']} | {o['agent']} ---\n{o['output'][:3000]}"
            for o in all_outputs
        )
        context = f"User request:\n{user_message}\n\nWork done so far:\n{outputs_text}"
        response = self._langchain_json().invoke([SystemMessage(content=system), HumanMessage(content=context)])
        raw = response.content if hasattr(response, "content") else str(response)
        evaluation = self._parse_json(raw)
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
        # Single agent, single iteration — return output directly to save an LLM call
        if len(all_outputs) == 1 and user_language == "English":
            self._log(run_id, "INFO", "Synthesis skipped — single agent output in English")
            return all_outputs[0]["output"]

        system = SYNTHESIS_SYSTEM_PROMPT.format(user_language=user_language)
        outputs_text = "\n\n".join(
            f"--- Iteration {o['iteration']} | {o['agent']} ---\n{o['output'][:3000]}"
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

    def _build_prior_context(self, all_outputs: list[dict]) -> str:
        if not all_outputs:
            return ""
        parts = []
        for o in all_outputs:
            parts.append(f"### Iteration {o['iteration']} — {o['agent']}\n{o['output'][:2000]}")
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

        output = self._runner().run(agent_name, full_description, expected_output, supports_tools)

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

            # Validate agents exist in registry
            valid_tasks = []
            for td in task_defs:
                if td.get("agent", "") in AGENT_REGISTRY:
                    valid_tasks.append(td)
                else:
                    msg = f"Agent '{td.get('agent')}' not in registry — skipped"
                    self._log(orchestrator_run.id, "WARNING", msg)
                    errors.append(msg)

            if not valid_tasks:
                self._log(orchestrator_run.id, "WARNING", "No valid agents — falling back to ProjectManagerAgent")
                valid_tasks = [{
                    "agent": "ProjectManagerAgent",
                    "description": user_message,
                    "expected_output": "A detailed, helpful response to the user's request",
                }]

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
                    ar = self._create_agent_run(
                        chat_id=chat_id,
                        agent_name=agent_name,
                        task_description=f"[Iter {iteration}] {td['description'][:100]}",
                        input_payload={"iteration": iteration, "description": td["description"]},
                    )
                    active_runs[agent_name] = ar
                    self._update_agent_run(ar, "running")

                    output = self._run_single_agent(
                        agent_name=agent_name,
                        task_description=td["description"],
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

                if not next_agent or next_agent not in AGENT_REGISTRY:
                    self._log(orchestrator_run.id, "WARNING", "evaluation_unknown_agent", {
                        "next_agent": next_agent,
                    })
                    break

                self._log(orchestrator_run.id, "INFO", "evaluation_continue", {
                    "next_agent": next_agent,
                    "reason": evaluation.get("reason", "")[:200],
                })
                current_tasks = [{"agent": next_agent, **next_task}]
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
