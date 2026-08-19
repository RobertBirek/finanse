import json

from pydantic import PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql+asyncpg://finanse:finanse@localhost:5432/finanse"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "change-me-in-production-use-a-real-secret-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: PositiveInt = 10080  # 7 days
    SESSION_EXPIRE_MINUTES: PositiveInt = 10080  # 7 days
    REGISTRATION_ENABLED: bool | None = None
    LOGIN_RATE_LIMIT: PositiveInt = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: PositiveInt = 60
    ADVISOR_RATE_LIMIT: PositiveInt = 30
    ADVISOR_RATE_LIMIT_WINDOW_SECONDS: PositiveInt = 60
    UPLOAD_RATE_LIMIT: PositiveInt = 10
    UPLOAD_RATE_LIMIT_WINDOW_SECONDS: PositiveInt = 60
    OPENAI_API_KEY: str = ""
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_MODEL: str = "deepseek-v4-pro"
    CORS_ORIGINS: str = "http://localhost:5173"
    ENVIRONMENT: str = "development"
    STIRLING_PDF_URL: str = "http://stirling-pdf:8080"

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            insecure_keys = {
                "",
                "change-me-in-production-use-a-real-secret-key",
                "change_me_to_random_64_chars",
                "dev-secret-key",
            }
            if self.SECRET_KEY in insecure_keys or len(self.SECRET_KEY.encode("utf-8")) < 32:
                raise ValueError(
                    "SECRET_KEY must be a non-placeholder value of at least 32 characters"
                )
        return self

    @property
    def registration_enabled(self) -> bool:
        return self.ENVIRONMENT != "production" and self.REGISTRATION_ENABLED is not False

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS.startswith("["):
            return json.loads(self.CORS_ORIGINS)
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def trusted_origins(self) -> list[str]:
        return self.cors_origins_list


settings = Settings()
