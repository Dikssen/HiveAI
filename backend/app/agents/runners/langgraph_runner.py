import time
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.tools import StructuredTool

from app.agents.runners.base import AgentRunner
from app.agents.agent_registry import AGENT_REGISTRY
from app.core.llm import get_langchain_llm

logger = structlog.get_logger()


def _wrap_crewai_tool(ct: Any) -> StructuredTool:
    schema = getattr(ct, "args_schema", None)

    def call(**kwargs: Any) -> str:
        return ct._run(**kwargs)

    return StructuredTool.from_function(
        func=call,
        name=ct.name,
        description=ct.description,
        args_schema=schema,
    )


def _strip_reasoning_hook(state: dict) -> dict:
    """
    DeepSeek thinking mode returns `reasoning_content` in AIMessages.
    When LangGraph passes history back to the API, it strips that field —
    causing a 400 error. We preemptively remove it before each LLM call.
    """
    cleaned = []
    for msg in state.get("messages", []):
        if isinstance(msg, AIMessage) and "reasoning_content" in msg.additional_kwargs:
            kwargs = {k: v for k, v in msg.additional_kwargs.items() if k != "reasoning_content"}
            msg = AIMessage(
                content=msg.content,
                additional_kwargs=kwargs,
                tool_calls=getattr(msg, "tool_calls", []),
                id=msg.id,
            )
        cleaned.append(msg)
    return {"messages": cleaned}


class LangGraphRunner(AgentRunner):
    def __init__(self):
        self._llm: Any = None

    def _get_llm(self) -> Any:
        if not self._llm:
            self._llm = get_langchain_llm(json_mode=False)
        return self._llm

    def run(self, agent_name: str, task_description: str, expected_output: str, supports_tools: bool) -> str:
        from langgraph.prebuilt import create_react_agent

        llm = self._get_llm()
        agent_impl = AGENT_REGISTRY[agent_name]

        system_prompt = (
            f"You are {agent_impl.role}.\n{agent_impl.backstory}\n\n"
            f"Goal: {agent_impl.goal}\n\n"
            f"Produce output that satisfies: {expected_output}"
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

        tools = [_wrap_crewai_tool(t) for t in agent_impl.get_tools()]
        graph = create_react_agent(
            llm, tools,
            prompt=system_prompt,
            pre_model_hook=_strip_reasoning_hook,
        )

        result = graph.invoke({"messages": [HumanMessage(content=task_description)]})
        elapsed = round(time.monotonic() - t0, 2)

        output = ""
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls", None):
                output = str(msg.content)
                break

        logger.info("agent_done", agent=agent_name, runner="langgraph",
                    elapsed_s=elapsed, output_chars=len(output))
        return output
