"""
Shared LLM module.
All agents and orchestrator get their LLM from here.
Supports Ollama, Anthropic, and OpenAI-compatible endpoints.
"""
import httpx
import structlog
from typing import Any
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.config import settings

logger = structlog.get_logger()


class _LLMLogger(BaseCallbackHandler):
    """Logs every request/response that goes to the LLM."""

    def on_chat_model_start(self, serialized: dict, messages: list, **kwargs: Any) -> None:
        for msg_list in messages:
            parts = []
            for msg in msg_list:
                role = getattr(msg, "type", "?")
                content = str(msg.content)
                parts.append({"role": role, "chars": len(content), "content": content})
            logger.info(
                "llm_request",
                model=serialized.get("kwargs", {}).get("model_name", settings.LLM_MODEL),
                messages=parts,
            )

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        for gen_list in response.generations:
            for gen in gen_list:
                text = getattr(gen, "text", None) or str(getattr(gen, "message", gen))
                llm_output = getattr(response, "llm_output", {}) or {}
                usage = llm_output.get("token_usage") or llm_output.get("usage")
                logger.info(
                    "llm_response",
                    chars=len(text),
                    content=text,
                    token_usage=usage,
                )

    def on_llm_error(self, error: Exception, **kwargs: Any) -> None:
        logger.error("llm_error", error=str(error))


_llm_logger = _LLMLogger()


def get_langchain_llm(
    json_mode: bool = False,
    extra_body: dict | None = None,
    temperature: float = 0.7,
):
    """
    Return a LangChain chat model for direct LLM calls (orchestrator decision).
    json_mode=True requests JSON output from the model.
    extra_body lets callers pass provider-specific OpenAI-compatible params.
    """
    if settings.LLM_PROVIDER == "ollama":
        from langchain_ollama import ChatOllama

        kwargs: dict = {
            "model": settings.LLM_MODEL,
            "base_url": settings.LLM_BASE_URL,
            "temperature": temperature,
            "callbacks": [_llm_logger],
        }
        if json_mode:
            kwargs["format"] = "json"
        return ChatOllama(**kwargs)

    elif settings.LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic

        # ChatAnthropic doesn't support response_format — JSON relies on system prompt
        return ChatAnthropic(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            temperature=temperature,
            callbacks=[_llm_logger],
        )

    else:
        from langchain_openai import ChatOpenAI

        merged_extra_body: dict = {}

        if not settings.LLM_ENABLE_THINKING:
            merged_extra_body["enable_thinking"] = False

        if extra_body:
            merged_extra_body.update(extra_body)

        kwargs: dict = {
            "model": settings.LLM_MODEL,
            "base_url": settings.LLM_BASE_URL,
            "api_key": settings.LLM_API_KEY or "sk-dummy",
            "temperature": temperature,
            "extra_body": merged_extra_body or None,
            "callbacks": [_llm_logger],
        }

        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}

        return ChatOpenAI(**kwargs)


def check_llm_health() -> dict:
    """Check if LLM is reachable and the configured model is available."""
    try:
        if settings.LLM_PROVIDER == "ollama":
            response = httpx.get(
                f"{settings.LLM_BASE_URL}/api/tags", timeout=5.0
            )
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                model_available = any(
                    settings.LLM_MODEL in name for name in model_names
                )
                return {
                    "status": "ok" if model_available else "model_not_found",
                    "provider": settings.LLM_PROVIDER,
                    "model": settings.LLM_MODEL,
                    "available_models": model_names,
                    "model_available": model_available,
                    "message": (
                        f"Model {settings.LLM_MODEL} is ready."
                        if model_available
                        else f"Model {settings.LLM_MODEL} not found. Run: ollama pull {settings.LLM_MODEL}"
                    ),
                }
            return {
                "status": "error",
                "provider": settings.LLM_PROVIDER,
                "model": settings.LLM_MODEL,
                "error": f"Ollama returned HTTP {response.status_code}",
                "message": f"Ollama returned unexpected status {response.status_code}. Is it running?",
            }
        elif settings.LLM_PROVIDER == "anthropic":
            response = httpx.get("https://api.anthropic.com", timeout=5.0)
            return {
                "status": "ok",
                "provider": settings.LLM_PROVIDER,
                "model": settings.LLM_MODEL,
                "message": "Anthropic endpoint reachable.",
            }
        else:
            # For other OpenAI-compatible providers just verify the URL is reachable
            response = httpx.get(settings.LLM_BASE_URL, timeout=5.0)
            return {
                "status": "ok",
                "provider": settings.LLM_PROVIDER,
                "model": settings.LLM_MODEL,
                "message": "LLM endpoint reachable.",
            }
    except httpx.ConnectError:
        return {
            "status": "error",
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL,
            "error": "Connection refused",
            "message": (
                f"Cannot connect to Ollama at {settings.LLM_BASE_URL}. "
                "Make sure Ollama is running locally: `ollama serve`"
            ),
        }
    except Exception as e:
        logger.error("LLM health check failed", error=str(e))
        return {
            "status": "error",
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL,
            "error": str(e),
            "message": f"Unexpected error checking LLM: {e}",
        }
