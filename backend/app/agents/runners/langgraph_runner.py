import time
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import StructuredTool

from app.agents.runners.base import AgentRunner
from app.agents.agent_registry import AGENT_REGISTRY
from app.core.llm import get_langchain_llm

logger = structlog.get_logger()

_TOOL_ERROR_PREFIX = "[TOOL_ERROR]"

_TOOL_ERROR_INSTRUCTION = (
    "\n\n--- TOOL ERROR POLICY ---\n"
    "If any tool returns a message starting with [TOOL_ERROR], you MUST:\n"
    "1. Stop immediately — do NOT call any other tools.\n"
    "2. Do NOT attempt workarounds or alternative approaches.\n"
    "3. Report the exact error message to the user as your final response.\n"
    "Your response must begin with: 'Tool error:' followed by the error details."
)

_NO_HALLUCINATION_INSTRUCTION = (
    "\n\n--- GROUNDING POLICY ---\n"
    "You MUST follow these rules at all times:\n"
    "1. Never invent, guess, or assume facts — only state what you retrieved via a tool or received in context.\n"
    "2. If you need specific data (code, files, tickets, metrics, etc.) and have no tool to fetch it — "
    "say explicitly: 'I don't have access to [X]. Please provide it or assign an agent that can retrieve it.'\n"
    "3. Do not fabricate file contents, function names, error messages, URLs, or numbers.\n"
    "4. If a tool returns data — use that data exactly. Do not paraphrase or expand it with invented details."
)


def _wrap_tool(ct: Any) -> StructuredTool:
    schema = getattr(ct, "args_schema", None)
    tool_name = getattr(ct, "name", type(ct).__name__)

    def call(**kwargs: Any) -> str:
        logger.info("tool_called", tool=tool_name, kwargs=str(kwargs)[:200])
        try:
            result = ct._run(**kwargs)
            logger.info("tool_done", tool=tool_name, result_preview=str(result)[:200])
            return result
        except Exception as e:
            logger.exception("tool_failed", tool=tool_name, error=str(e))
            return (
                f"{_TOOL_ERROR_PREFIX} Tool '{tool_name}' failed.\n"
                f"{str(e)}\n"
                f"STOP. Do not retry. Do not use other tools. Report this error to the user."
            )

    return StructuredTool.from_function(
        func=call,
        name=ct.name,
        description=ct.description,
        args_schema=schema,
    )


def _extract_tool_errors(messages: list) -> list[str]:
    return [
        msg.content for msg in messages
        if isinstance(msg, ToolMessage) and msg.content.startswith(_TOOL_ERROR_PREFIX)
    ]


class LangGraphRunner(AgentRunner):
    def __init__(self):
        self._llm_cache: dict[tuple, Any] = {}

    def _get_llm(self, *, supports_tools: bool = False, temperature: float = 0.7) -> Any:
        key = (supports_tools, round(temperature, 3))
        if key not in self._llm_cache:
            if supports_tools:
                self._llm_cache[key] = get_langchain_llm(
                    json_mode=False,
                    temperature=temperature,
                    extra_body={"thinking": {"type": "disabled"}},
                )
            else:
                self._llm_cache[key] = get_langchain_llm(
                    json_mode=False,
                    temperature=temperature,
                )
        return self._llm_cache[key]

    def _get_agent_temperature(self, agent_name: str, db: Any) -> float:
        if db is None:
            return 0.7
        try:
            from app.models.agent import Agent
            row = db.query(Agent).filter(Agent.name == agent_name).first()
            return float(row.temperature) if row else 0.7
        except Exception:
            return 0.7

    def run(self, agent_name: str, task_description: str, expected_output: str, supports_tools: bool, db=None, chat_id=None) -> str:
        from langgraph.prebuilt import create_react_agent

        temperature = self._get_agent_temperature(agent_name, db)
        llm = self._get_llm(supports_tools=supports_tools, temperature=temperature)
        agent_impl = AGENT_REGISTRY[agent_name]

        system_prompt = (
            f"You are {agent_impl.role}.\n{agent_impl.backstory}\n\n"
            f"Goal: {agent_impl.goal}\n\n"
            f"Produce output that satisfies: {expected_output}"
            + _TOOL_ERROR_INSTRUCTION
            + _NO_HALLUCINATION_INSTRUCTION
        )

        logger.info("agent_start", agent=agent_name, runner="langgraph", tools=supports_tools,
                    task_preview=task_description[:120])
        t0 = time.monotonic()

        if not supports_tools:
            from langchain_core.output_parsers import StrOutputParser
            chain = llm | StrOutputParser()
            output = chain.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=task_description),
            ])
            elapsed = round(time.monotonic() - t0, 2)
            logger.info("agent_done", agent=agent_name, runner="langgraph",
                        elapsed_s=elapsed, output_chars=len(output))
            return output

        active_tools = agent_impl.get_active_tools(db, chat_id=chat_id) if db is not None else agent_impl.get_tools()
        tools = [_wrap_tool(t) for t in active_tools]
        graph = create_react_agent(llm, tools, prompt=system_prompt)

        result = graph.invoke({"messages": [HumanMessage(content=task_description)]})
        elapsed = round(time.monotonic() - t0, 2)

        messages = result.get("messages", [])

        # Extract AI final answer
        output = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls", None):
                output = str(msg.content)
                break

        # If tool errors occurred and agent didn't surface them clearly — do it ourselves
        tool_errors = _extract_tool_errors(messages)
        if tool_errors:
            error_mentioned = any(
                kw in output.lower()
                for kw in ("error", "failed", "не вдалося", "помилка", "tool error")
            )
            if not error_mentioned:
                output = f"Tool error:\n\n{tool_errors[-1]}"
                logger.warning("agent_ignored_tool_error", agent=agent_name,
                               error_preview=tool_errors[-1][:200])

        logger.info("agent_done", agent=agent_name, runner="langgraph",
                    elapsed_s=elapsed, output_chars=len(output))
        return output
