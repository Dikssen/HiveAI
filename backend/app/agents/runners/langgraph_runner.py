from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool

from app.agents.runners.base import AgentRunner
from app.agents.agent_registry import AGENT_REGISTRY
from app.core.llm import get_langchain_llm


def _wrap_crewai_tool(ct: Any) -> StructuredTool:
    """Convert a CrewAI tool to a LangChain StructuredTool."""
    schema = getattr(ct, "args_schema", None)

    def call(**kwargs: Any) -> str:
        return ct._run(**kwargs)

    return StructuredTool.from_function(
        func=call,
        name=ct.name,
        description=ct.description,
        args_schema=schema,
    )


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

        if supports_tools:
            tools = [_wrap_crewai_tool(t) for t in agent_impl.get_tools()]
            graph = create_react_agent(llm, tools, prompt=system_prompt)
        else:
            # No tool calling — plain chat chain
            from langchain_core.output_parsers import StrOutputParser
            chain = llm | StrOutputParser()
            return chain.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=task_description),
            ])

        result = graph.invoke({"messages": [HumanMessage(content=task_description)]})
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.content and not getattr(msg, "tool_calls", None):
                return str(msg.content)
        return ""
