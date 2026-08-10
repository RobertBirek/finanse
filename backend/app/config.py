from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql+asyncpg://finanse:finanse@localhost:5432/finanse"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "change-me-in-production-use-a-real-secret-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    OPENAI_API_KEY: str = ""
    CORS_ORIGINS: List[str] = ["http://localhost:5173"]
    ENVIRONMENT: str = "development"
    STIRLING_PDF_URL: str = "http://stirling-pdf:8080"


settings = Settings()
