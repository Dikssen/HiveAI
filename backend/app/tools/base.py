"""
Base tool class with structured metadata.
All tools extend BaseTool from crewai.tools and add logging support.
"""
import json
import structlog
from crewai.tools import BaseTool as CrewBaseTool

logger = structlog.get_logger()


class LoggedTool(CrewBaseTool):
    """CrewAI BaseTool that logs every invocation."""

    def _run(self, *args, **kwargs):
        raise NotImplementedError

    def _sanitize_input(self, tool_input):
        """
        Some LLMs (e.g. DeepSeek) send a JSON array containing both the tool
        call input AND the hallucinated result in one list, e.g.:
          [{"repo_name": "x"}, {"success": true, ...}]
        CrewAI rejects lists. We extract the first dict that looks like real
        input (has schema fields, no "success" key).
        """
        raw = tool_input
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return tool_input  # unparseable string — let super() handle it

        if not isinstance(raw, list):
            return tool_input  # already a plain dict or string — no fix needed

        schema_fields: set = set()
        if hasattr(self, "args_schema") and self.args_schema:
            schema_fields = set(self.args_schema.model_fields.keys())

        # Prefer a dict that has schema keys and no "success" (result indicator)
        for item in raw:
            if isinstance(item, dict) and "success" not in item:
                if not schema_fields or any(k in schema_fields for k in item):
                    logger.warning(
                        "Tool input was a list — extracted first valid dict",
                        tool=self.name,
                        extracted=item,
                    )
                    return json.dumps(item) if isinstance(tool_input, str) else item

        # Fallback: first dict in the list
        for item in raw:
            if isinstance(item, dict):
                logger.warning(
                    "Tool input was a list — fallback to first dict",
                    tool=self.name,
                    extracted=item,
                )
                return json.dumps(item) if isinstance(tool_input, str) else item

        return tool_input  # give up, pass as-is

    def run(self, *args, **kwargs):
        args = list(args)
        if args:
            args[0] = self._sanitize_input(args[0])
        elif "tool_input" in kwargs:
            kwargs["tool_input"] = self._sanitize_input(kwargs["tool_input"])

        logger.info("Tool called", tool=self.name, args=str(args)[:200], kwargs=str(kwargs)[:200])
        try:
            result = super().run(*args, **kwargs)
            logger.info("Tool completed", tool=self.name, result_preview=str(result)[:200])
            return result
        except Exception as e:
            logger.error("Tool failed", tool=self.name, error=str(e))
            return f"[Tool error in {self.name}]: {e}"
