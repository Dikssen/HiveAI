from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://itcompany:itcompany@localhost:5432/itcompany"
    REDIS_URL: str = "redis://localhost:6379/0"

    LLM_PROVIDER: str = "ollama"
    LLM_MODEL: str = "qwen2.5:14b"
    LLM_BASE_URL: str = "http://localhost:11434"
    LLM_API_KEY: Optional[str] = None
    LLM_SUPPORTS_TOOLS: bool = True

    LOG_LEVEL: str = "INFO"
    SAMPLE_DATA_PATH: str = "./sample_data"

    GITHUB_TOKEN: Optional[str] = None

    MAX_ORCHESTRATOR_ITERATIONS: int = 10

    # Runner backends: "crewai" | "langgraph"
    AGENT_RUNNER: str = "crewai"
    # Orchestrator backend: "custom" | "langgraph"
    ORCHESTRATOR_RUNNER: str = "custom"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
