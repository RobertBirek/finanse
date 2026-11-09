import ipaddress
import json
import re
from typing import Any
from urllib.parse import urlsplit

from pydantic import Field, PositiveFloat, PositiveInt, PrivateAttr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CORS_ORIGINS = "http://localhost:5173"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def __init__(self, **values: Any) -> None:
        if "CORS_ORIGINS" in values and "TRUSTED_ORIGINS" not in values:
            values["TRUSTED_ORIGINS"] = values["CORS_ORIGINS"]
        super().__init__(**values)

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
    DOCUMENT_JOB_TIMEOUT_SECONDS: PositiveInt = 600
    DOCUMENT_STALE_PROCESSING_SECONDS: PositiveInt = 900
    DOCUMENT_DISPATCH_BATCH_SIZE: PositiveInt = 100
    DOCUMENT_MAX_FILE_BYTES: PositiveInt = 20 * 1024 * 1024
    DOCUMENT_MAX_BODY_BYTES: PositiveInt = 21 * 1024 * 1024
    DOCUMENT_PARSER_MEMORY_BYTES: PositiveInt = 512 * 1024 * 1024
    DOCUMENT_PARSER_CPU_SECONDS: PositiveInt = 10
    DOCUMENT_PARSER_TIMEOUT_SECONDS: PositiveFloat = 15
    DOCUMENT_VALIDATION_CONCURRENCY: PositiveInt = 2
    DOCUMENT_VALIDATION_QUEUE_SECONDS: PositiveFloat = 2
    DOCUMENT_MAX_PAGES: PositiveInt = 100
    FINANCE_IMPORT_MAX_CSV_ROWS: PositiveInt = 100000
    FINANCE_IMPORT_MAX_TEXT_CHARS: PositiveInt = 2 * 1024 * 1024
    FINANCE_IMPORT_MAX_ATTEMPTS: PositiveInt = 3
    FINANCE_IMPORT_LEASE_SECONDS: PositiveInt = 180
    FINANCE_IMPORT_RETRY_SECONDS: PositiveInt = 30
    FINANCE_IMPORT_DISPATCH_BATCH: PositiveInt = 20
    DOCUMENT_MAX_IMAGE_PIXELS: PositiveInt = 25_000_000
    DOCUMENT_IMAGE_OUTPUT_MAX_BYTES: PositiveInt = 20 * 1024 * 1024
    DOCUMENT_JPEG_QUALITY: PositiveInt = 90
    DOCUMENT_PREVIEW_MAX_EDGE: PositiveInt = 1600
    DOCUMENT_USER_QUOTA_BYTES: PositiveInt = 1024 * 1024 * 1024
    DOCUMENT_GLOBAL_QUOTA_BYTES: PositiveInt = 10 * 1024 * 1024 * 1024
    DOCUMENT_MIN_FREE_BYTES: PositiveInt = 1024 * 1024 * 1024
    DOCUMENT_OCR_MAX_BYTES: PositiveInt = 64 * 1024 * 1024
    DOCUMENT_OCR_TEXT_MAX_BYTES: PositiveInt = 2 * 1024 * 1024
    DOCUMENT_MAX_ATTEMPTS: PositiveInt = 3
    DOCUMENT_RETRY_DELAYS_SECONDS: tuple[PositiveInt, ...] = (30, 120)
    DOCUMENT_VISION_ENABLED: bool = False
    DOCUMENT_VISION_PROVIDER: str = ""
    DOCUMENT_VISION_BASE_URL: str = ""
    DOCUMENT_VISION_MODEL: str = ""
    DOCUMENT_VISION_API_KEY: str = ""
    DOCUMENT_VISION_PROMPT_VERSION: str = ""
    DOCUMENT_VISION_SCHEMA_VERSION: str = ""
    DOCUMENT_VISION_MAX_EDGE: PositiveInt = 2048
    DOCUMENT_VISION_MAX_BYTES: PositiveInt = 4 * 1024 * 1024
    DOCUMENT_VISION_MAX_OUTPUT_TOKENS: PositiveInt = 1600
    DOCUMENT_VISION_REASONING_EFFORT: str = "none"
    DOCUMENT_VISION_TIMEOUT_SECONDS: PositiveFloat = 60
    DOCUMENT_VISION_CONCURRENCY: PositiveInt = 2
    DOCUMENT_VISION_MAX_ATTEMPTS: PositiveInt = 2
    DOCUMENT_VISION_RETRY_DELAYS_SECONDS: tuple[PositiveInt, ...] = (30,)
    DOCUMENT_VISION_DAILY_CALL_LIMIT_PER_USER: PositiveInt = 50
    DOCUMENT_VISION_LEASE_SECONDS: PositiveInt = 120
    DOCUMENT_RECEIPT_ITEMS_ENABLED: bool = False
    DOCUMENT_RECEIPT_ITEMS_PROVIDER: str = ""
    DOCUMENT_RECEIPT_ITEMS_BASE_URL: str = ""
    DOCUMENT_RECEIPT_ITEMS_MODEL: str = ""
    DOCUMENT_RECEIPT_ITEMS_API_KEY: str = ""
    DOCUMENT_RECEIPT_ITEMS_PROMPT_VERSION: str = ""
    DOCUMENT_RECEIPT_ITEMS_SCHEMA_VERSION: str = ""
    DOCUMENT_RECEIPT_ITEMS_MAX_EDGE: PositiveInt = Field(default=4096, le=8192)
    DOCUMENT_RECEIPT_ITEMS_MAX_BYTES: PositiveInt = 4 * 1024 * 1024
    DOCUMENT_RECEIPT_ITEMS_MAX_PIXELS: PositiveInt = 16_777_216
    DOCUMENT_RECEIPT_ITEMS_MAX_OUTPUT_TOKENS: PositiveInt = Field(default=8192, le=32768)
    DOCUMENT_RECEIPT_ITEMS_MAX_RESPONSE_BYTES: PositiveInt = Field(default=262144, le=1048576)
    DOCUMENT_RECEIPT_ITEMS_REASONING_EFFORT: str = "none"
    DOCUMENT_RECEIPT_ITEMS_TIMEOUT_SECONDS: PositiveFloat = 60
    DOCUMENT_RECEIPT_ITEMS_CONCURRENCY: PositiveInt = Field(default=2, le=8)
    DOCUMENT_RECEIPT_ITEMS_PREPARE_MAX_ATTEMPTS: PositiveInt = Field(default=2, le=4)
    DOCUMENT_RECEIPT_ITEMS_PREPARE_RETRY_SECONDS: PositiveInt = 30
    DOCUMENT_RECEIPT_ITEMS_LEASE_SECONDS: PositiveInt = 180
    DOCUMENT_RECEIPT_ITEMS_DISPATCH_BATCH: PositiveInt = Field(default=25, le=100)
    DOCUMENT_RECEIPT_ITEMS_QUEUE_LIMIT_PER_USER: PositiveInt = Field(default=10, le=100)
    DOCUMENT_RECEIPT_ITEMS_QUEUE_LIMIT_GLOBAL: PositiveInt = Field(default=100, le=1000)
    DOCUMENT_RECEIPT_ITEMS_DAILY_CALL_LIMIT_PER_USER: PositiveInt = Field(default=10, le=1000)
    DOCUMENT_RECEIPT_ITEMS_DAILY_CALL_LIMIT_GLOBAL: PositiveInt = Field(default=100, le=10000)
    DOCUMENT_RECEIPT_ITEMS_POLL_MS: PositiveInt = Field(default=2000, ge=1000, le=30000)
    DOCUMENT_RECEIPT_ITEMS_PAGE_SIZE: PositiveInt = Field(default=25, le=100)
    BILL_PAYMENT_CANDIDATE_DATE_WINDOW_DAYS: PositiveInt = 30
    FINANCE_CATEGORY_SPLIT_MAX_PARTS: PositiveInt = 50
    FINANCE_RULE_DESCRIPTION_MAX_CHARS: PositiveInt = Field(default=500, le=2000)
    FINANCE_RULE_DISPATCH_BATCH: PositiveInt = 50
    FINANCE_RULE_LEASE_SECONDS: PositiveInt = 60
    FINANCE_RULE_MAX_ATTEMPTS: PositiveInt = 3
    FINANCE_RULE_RETRY_INITIAL_SECONDS: PositiveInt = 10
    FINANCE_RULE_RETRY_LATER_SECONDS: PositiveInt = 60
    FINANCE_RULE_UI_POLL_MS: PositiveInt = 2000
    FINANCE_SUGGESTIONS_ENABLED: bool = False
    FINANCE_SUGGESTIONS_PROVIDER: str = ""
    FINANCE_SUGGESTIONS_BASE_URL: str = ""
    FINANCE_SUGGESTIONS_MODEL: str = ""
    FINANCE_SUGGESTIONS_API_KEY: str = Field(default="", repr=False)
    FINANCE_SUGGESTIONS_DESCRIPTION_MAX_CHARS: PositiveInt = Field(default=500, le=2000)
    FINANCE_SUGGESTIONS_MAX_CATEGORIES: PositiveInt = Field(default=200, le=1000)
    FINANCE_SUGGESTIONS_MAX_REQUEST_BYTES: PositiveInt = Field(default=32768, le=262144)
    FINANCE_SUGGESTIONS_MAX_OUTPUT_TOKENS: PositiveInt = Field(default=1024, le=8192)
    FINANCE_SUGGESTIONS_EXPLANATION_MAX_CHARS: PositiveInt = Field(default=500, le=2000)
    FINANCE_SUGGESTIONS_NEW_CATEGORY_MAX_CHARS: PositiveInt = Field(default=80, le=200)
    FINANCE_SUGGESTIONS_DAILY_CALL_LIMIT: PositiveInt = Field(default=5, le=1000)
    FINANCE_SUGGESTIONS_TTL_DAYS: PositiveInt = Field(default=7, le=365)
    FINANCE_SUGGESTIONS_MAX_JOB_AGE_HOURS: PositiveInt = Field(default=24, le=168)
    FINANCE_SUGGESTIONS_REVIEW_PAGE_SIZE: PositiveInt = Field(default=20, le=100)
    FINANCE_SUGGESTIONS_TIMEOUT_SECONDS: PositiveFloat = 30
    FINANCE_SUGGESTIONS_LEASE_SECONDS: PositiveInt = 90
    FINANCE_SUGGESTIONS_JOB_TIMEOUT_SECONDS: PositiveInt = 120
    FINANCE_SUGGESTIONS_MAX_ATTEMPTS: PositiveInt = 3
    FINANCE_SUGGESTIONS_RETRY_INITIAL_SECONDS: PositiveInt = 10
    FINANCE_SUGGESTIONS_RETRY_LATER_SECONDS: PositiveInt = 60
    FINANCE_SUGGESTIONS_DISPATCH_BATCH: PositiveInt = Field(default=20, le=100)
    FINANCE_SUGGESTIONS_UI_POLL_MS: PositiveInt = 2000
    FINANCE_RECEIPT_MAX_LINES: PositiveInt = Field(default=200, le=1000)
    FINANCE_RECEIPT_MAX_DISCOUNTS: PositiveInt = Field(default=50, le=200)
    FINANCE_RECEIPT_MAX_DISCOUNT_SHARES: PositiveInt = Field(default=1000, le=5000)
    FINANCE_RECEIPT_ITEM_NAME_MAX_CHARS: PositiveInt = Field(default=300, le=2000)
    FINANCE_RECEIPT_STORE_NAME_MAX_CHARS: PositiveInt = Field(default=200, le=500)
    FINANCE_RECEIPT_HISTORY_PAGE_SIZE: PositiveInt = Field(default=5, le=20)
    FINANCE_RECEIPT_HISTORY_SCAN_LIMIT: PositiveInt = Field(default=200, le=2000)
    FINANCE_RECEIPT_HISTORY_PREFIX_MIN_CHARS: PositiveInt = Field(default=4, le=50)
    FINANCE_RECEIPT_STORE_PAGE_SIZE: PositiveInt = Field(default=50, le=100)
    UPLOAD_RATE_LIMIT: PositiveInt = 10
    UPLOAD_RATE_LIMIT_WINDOW_SECONDS: PositiveInt = 60
    DOCUMENT_PROCESSING_ACTION_RATE_LIMIT: PositiveInt = 10
    DOCUMENT_PROCESSING_ACTION_RATE_LIMIT_WINDOW_SECONDS: PositiveInt = 60
    OPENAI_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = ""
    LLM_PROVIDER: str = "openai"
    LLM_MAX_OUTPUT_TOKENS: PositiveInt = 4096
    LLM_REASONING_EFFORT: str = "low"
    DOCUMENT_TEXT_MODEL: str = ""
    DOCUMENT_TEXT_MAX_OUTPUT_TOKENS: PositiveInt = 2000
    DOCUMENT_TEXT_REASONING_EFFORT: str = "none"
    CORS_ORIGINS: str = DEFAULT_CORS_ORIGINS
    TRUSTED_ORIGINS: str | None = None
    TRUSTED_PROXY_HOSTS: str = "frontend"
    ENVIRONMENT: str = "development"
    STIRLING_PDF_URL: str = "http://stirling-pdf:8080"

    _trusted_origins: tuple[str, ...] = PrivateAttr(default=())
    _trusted_proxy_hosts: tuple[str, ...] = PrivateAttr(default=())

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

    @classmethod
    def _validate_trusted_proxy_hosts(cls, hosts: str) -> tuple[str, ...]:
        return tuple(
            cls._normalize_hostname(host.strip()) for host in hosts.split(",") if host.strip()
        )

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.DOCUMENT_RECEIPT_ITEMS_MAX_BYTES > self.DOCUMENT_IMAGE_OUTPUT_MAX_BYTES:
            raise ValueError("Receipt image byte limit exceeds the normalizer safety bound")
        if self.DOCUMENT_RECEIPT_ITEMS_MAX_PIXELS > self.DOCUMENT_MAX_IMAGE_PIXELS:
            raise ValueError("Receipt image pixel budget exceeds the parser safety bound")
        if (
            self.DOCUMENT_RECEIPT_ITEMS_LEASE_SECONDS
            <= self.DOCUMENT_PARSER_TIMEOUT_SECONDS
            + self.DOCUMENT_RECEIPT_ITEMS_TIMEOUT_SECONDS
            + 30
        ):
            raise ValueError("Receipt read lease must exceed preparation and HTTP deadlines")
        if self.DOCUMENT_JOB_TIMEOUT_SECONDS <= self.DOCUMENT_RECEIPT_ITEMS_LEASE_SECONDS:
            raise ValueError("Worker timeout must exceed the receipt read lease")
        if (
            self.DOCUMENT_RECEIPT_ITEMS_DAILY_CALL_LIMIT_GLOBAL
            < self.DOCUMENT_RECEIPT_ITEMS_DAILY_CALL_LIMIT_PER_USER
            or self.DOCUMENT_RECEIPT_ITEMS_QUEUE_LIMIT_GLOBAL
            < self.DOCUMENT_RECEIPT_ITEMS_QUEUE_LIMIT_PER_USER
        ):
            raise ValueError("Global receipt limits must cover per-user limits")
        if self.FINANCE_RECEIPT_HISTORY_SCAN_LIMIT < self.FINANCE_RECEIPT_HISTORY_PAGE_SIZE:
            raise ValueError("Receipt history scan limit must cover a result page")
        if self.FINANCE_SUGGESTIONS_LEASE_SECONDS <= self.FINANCE_SUGGESTIONS_TIMEOUT_SECONDS + 10:
            raise ValueError("Suggestion lease must exceed provider timeout plus safety margin")
        if self.FINANCE_SUGGESTIONS_JOB_TIMEOUT_SECONDS <= self.FINANCE_SUGGESTIONS_LEASE_SECONDS:
            raise ValueError("Suggestion job timeout must exceed lease")
        if len(self.DOCUMENT_RETRY_DELAYS_SECONDS) != self.DOCUMENT_MAX_ATTEMPTS - 1:
            raise ValueError("Retry delay count must equal max attempts minus one")
        if self.DOCUMENT_MAX_BODY_BYTES <= self.DOCUMENT_MAX_FILE_BYTES:
            raise ValueError("Upload body limit must exceed file limit for multipart overhead")
        if self.DOCUMENT_STALE_PROCESSING_SECONDS <= self.DOCUMENT_JOB_TIMEOUT_SECONDS:
            raise ValueError("Document recovery timeout must exceed worker job timeout")
        if len(self.DOCUMENT_VISION_RETRY_DELAYS_SECONDS) != self.DOCUMENT_VISION_MAX_ATTEMPTS - 1:
            raise ValueError("Vision retry delay count must equal attempts minus one")
        if self.DOCUMENT_VISION_MAX_BYTES > self.DOCUMENT_IMAGE_OUTPUT_MAX_BYTES:
            raise ValueError("Vision image limit cannot exceed image output limit")
        if self.DOCUMENT_VISION_LEASE_SECONDS <= (
            self.DOCUMENT_VISION_TIMEOUT_SECONDS + self.DOCUMENT_PARSER_TIMEOUT_SECONDS
        ):
            raise ValueError("Vision lease must exceed provider and parser timeouts")
        if self.DOCUMENT_JOB_TIMEOUT_SECONDS <= self.DOCUMENT_VISION_LEASE_SECONDS:
            raise ValueError("Document job timeout must exceed vision lease")
        if self.DOCUMENT_VISION_BASE_URL:
            parsed_vision_url = urlsplit(self.DOCUMENT_VISION_BASE_URL)
            if (
                parsed_vision_url.scheme != "https"
                or not parsed_vision_url.hostname
                or parsed_vision_url.username is not None
                or parsed_vision_url.password is not None
                or parsed_vision_url.query
                or parsed_vision_url.fragment
            ):
                raise ValueError(
                    "DOCUMENT_VISION_BASE_URL must be an HTTPS URL without credentials"
                )
        raw_origins = self.TRUSTED_ORIGINS
        source_name = "TRUSTED_ORIGINS"
        if raw_origins is None:
            raw_origins = self.CORS_ORIGINS
            source_name = "CORS_ORIGINS"
        self._trusted_origins = self._validate_trusted_origins(
            self._parse_origins(raw_origins, source_name)
        )
        self._trusted_proxy_hosts = self._validate_trusted_proxy_hosts(self.TRUSTED_PROXY_HOSTS)

        if self.ENVIRONMENT == "production":
            if not self.trusted_proxy_hosts:
                raise ValueError("TRUSTED_PROXY_HOSTS must contain at least one host in production")
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

    @property
    def trusted_proxy_hosts(self) -> tuple[str, ...]:
        return self._trusted_proxy_hosts


settings = Settings()
