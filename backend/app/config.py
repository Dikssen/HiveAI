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

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
