import json
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql+asyncpg://finanse:finanse@localhost:5432/finanse"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "change-me-in-production-use-a-real-secret-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days
    OPENAI_API_KEY: str = ""
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_MODEL: str = "deepseek-v4-pro"
    CORS_ORIGINS: str = "http://localhost:5173"
    ENVIRONMENT: str = "development"
    STIRLING_PDF_URL: str = "http://stirling-pdf:8080"

    @property
    def cors_origins_list(self) -> List[str]:
        if self.CORS_ORIGINS.startswith("["):
            return json.loads(self.CORS_ORIGINS)
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
