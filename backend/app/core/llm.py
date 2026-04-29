"""
Shared LLM module.
All agents and orchestrator get their LLM from here.
Supports Ollama (default) and OpenAI-compatible endpoints.
"""
import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()


def get_crewai_llm():
    """Return a CrewAI LLM instance (uses LiteLLM under the hood)."""
    from crewai import LLM

    if settings.LLM_PROVIDER == "ollama":
        return LLM(
            model=f"ollama/{settings.LLM_MODEL}",
            base_url=settings.LLM_BASE_URL,
        )
    else:
        # OpenAI-compatible endpoint
        return LLM(
            model=settings.LLM_MODEL,
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY or "sk-dummy",
        )


def get_langchain_llm(json_mode: bool = False):
    """
    Return a LangChain chat model for direct LLM calls (orchestrator decision).
    json_mode=True requests JSON output from the model.
    """
    if settings.LLM_PROVIDER == "ollama":
        from langchain_ollama import ChatOllama

        kwargs: dict = {
            "model": settings.LLM_MODEL,
            "base_url": settings.LLM_BASE_URL,
        }
        if json_mode:
            kwargs["format"] = "json"
        return ChatOllama(**kwargs)
    else:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.LLM_MODEL,
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY or "sk-dummy",
        )


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
        else:
            # For non-Ollama providers just verify the URL is reachable
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
