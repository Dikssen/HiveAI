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


def _wrap_crewai_tool(ct: Any) -> StructuredTool:
    schema = getattr(ct, "args_schema", None)
    tool_name = getattr(ct, "name", type(ct).__name__)

    def call(**kwargs: Any) -> str:
        try:
            return ct._run(**kwargs)
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
        if isinstance(msg, ToolMessage) and _TOOL_ERROR_PREFIX in msg.content
    ]


class LangGraphRunner(AgentRunner):
    def __init__(self):
        self._tool_llm: Any = None
        self._llm: Any = None

    def _get_llm(self, *, supports_tools: bool = False) -> Any:
        if supports_tools:
            if not self._tool_llm:
                self._tool_llm = get_langchain_llm(
                    json_mode=False,
                    extra_body={"thinking": {"type": "disabled"}},
                )
            return self._tool_llm

        if not self._llm:
            self._llm = get_langchain_llm(json_mode=False)

        return self._llm

    def run(self, agent_name: str, task_description: str, expected_output: str, supports_tools: bool, db=None) -> str:
        from langgraph.prebuilt import create_react_agent

        llm = self._get_llm(supports_tools=supports_tools)
        agent_impl = AGENT_REGISTRY[agent_name]

        system_prompt = (
            f"You are {agent_impl.role}.\n{agent_impl.backstory}\n\n"
            f"Goal: {agent_impl.goal}\n\n"
            f"Produce output that satisfies: {expected_output}"
            + _TOOL_ERROR_INSTRUCTION
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

        active_tools = agent_impl.get_active_tools(db) if db is not None else agent_impl.get_tools()
        tools = [_wrap_crewai_tool(t) for t in active_tools]
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
