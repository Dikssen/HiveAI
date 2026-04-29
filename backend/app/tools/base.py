"""
Base tool class with structured metadata.
All tools extend BaseTool from crewai.tools and add logging support.
"""
import structlog
from crewai.tools import BaseTool as CrewBaseTool

logger = structlog.get_logger()


class LoggedTool(CrewBaseTool):
    """CrewAI BaseTool that logs every invocation."""

    def _run(self, *args, **kwargs):
        raise NotImplementedError

    def run(self, *args, **kwargs):
        logger.info("Tool called", tool=self.name, args=str(args)[:200], kwargs=str(kwargs)[:200])
        try:
            result = super().run(*args, **kwargs)
            logger.info("Tool completed", tool=self.name, result_preview=str(result)[:200])
            return result
        except Exception as e:
            logger.error("Tool failed", tool=self.name, error=str(e))
            return f"[Tool error in {self.name}]: {e}"
