import ipaddress
import json
import re
from typing import Any
from urllib.parse import urlsplit

from pydantic import PositiveInt, PrivateAttr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CORS_ORIGINS = "http://localhost:5173"


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
    CORS_ORIGINS: str = DEFAULT_CORS_ORIGINS
    TRUSTED_ORIGINS: str | None = None
    ENVIRONMENT: str = "development"
    STIRLING_PDF_URL: str = "http://stirling-pdf:8080"

    _trusted_origins: tuple[str, ...] = PrivateAttr(default=())

    @staticmethod
    def _parse_origins(value: Any, setting_name: str) -> list[str]:
        if not isinstance(value, str):
            raise TypeError(f"{setting_name} must be a comma-separated string or JSON list")

        stripped = value.strip()
        if stripped.startswith(("[", "{", '"')):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as error:
                raise ValueError(f"{setting_name} must contain valid JSON") from error
            if not isinstance(parsed, list) or not all(
                isinstance(origin, str) for origin in parsed
            ):
                raise ValueError(f"{setting_name} JSON must be a list of strings")
            return parsed
        return value.split(",")

    @staticmethod
    def _normalize_hostname(hostname: str) -> str:
        host = hostname.lower()
        if host == "localhost":
            return host

        try:
            ipaddress.ip_address(host)
            return host
        except ValueError:
            pass

        if host.replace(".", "").isdigit() or len(host) > 253:
            raise ValueError("TRUSTED_ORIGINS contains an invalid hostname")

        label_pattern = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
        if not all(label_pattern.fullmatch(label) for label in host.split(".")):
            raise ValueError("TRUSTED_ORIGINS contains an invalid hostname")
        return host

    @classmethod
    def _validate_trusted_origins(cls, origins: list[str]) -> tuple[str, ...]:
        if not origins:
            raise ValueError("TRUSTED_ORIGINS must contain at least one origin")

        normalized: list[str] = []
        for origin in origins:
            value = origin.strip()
            if not value or "%" in value or "\\" in value:
                raise ValueError("TRUSTED_ORIGINS cannot contain empty origins")

            try:
                parsed = urlsplit(value)
                port = parsed.port
            except ValueError as error:
                raise ValueError("TRUSTED_ORIGINS contains an invalid origin") from error

            if (
                parsed.scheme.lower() not in {"http", "https"}
                or not parsed.hostname
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username is not None
                or parsed.password is not None
                or port == 0
            ):
                raise ValueError("TRUSTED_ORIGINS contains an invalid origin")

            host = cls._normalize_hostname(parsed.hostname)
            if ":" in host:
                host = f"[{host}]"
            normalized_origin = f"{parsed.scheme.lower()}://{host}"
            if port is not None:
                normalized_origin = f"{normalized_origin}:{port}"
            if normalized_origin in normalized:
                raise ValueError("TRUSTED_ORIGINS cannot contain duplicate origins")
            normalized.append(normalized_origin)

        return tuple(normalized)

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        raw_origins = self.TRUSTED_ORIGINS
        source_name = "TRUSTED_ORIGINS"
        if raw_origins is None:
            raw_origins = self.CORS_ORIGINS
            source_name = "CORS_ORIGINS"
        self._trusted_origins = self._validate_trusted_origins(
            self._parse_origins(raw_origins, source_name)
        )

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
            if any(not origin.startswith("https://") for origin in self.trusted_origins):
                raise ValueError("TRUSTED_ORIGINS must use HTTPS in production")
        return self

    @property
    def registration_enabled(self) -> bool:
        return self.ENVIRONMENT != "production" and self.REGISTRATION_ENABLED is not False

    @property
    def cors_origins_list(self) -> list[str]:
        return list(self.trusted_origins)

    @property
    def trusted_origins(self) -> tuple[str, ...]:
        return self._trusted_origins


settings = Settings()
