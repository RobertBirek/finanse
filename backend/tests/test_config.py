import json

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize(
    "secret_key",
    ["", "change-me-in-production-use-a-real-secret-key", "x" * 31],
)
def test_production_requires_a_strong_non_placeholder_secret(secret_key: str) -> None:
    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT="production", SECRET_KEY=secret_key)


def test_production_accepts_a_distinct_32_character_secret() -> None:
    settings = Settings(ENVIRONMENT="production", SECRET_KEY="s" * 32)

    assert settings.SECRET_KEY == "s" * 32


def test_production_always_disables_registration() -> None:
    settings = Settings(ENVIRONMENT="production", SECRET_KEY="s" * 32, REGISTRATION_ENABLED=True)

    assert settings.registration_enabled is False


def test_development_registration_defaults_to_enabled_and_can_be_disabled() -> None:
    assert Settings(ENVIRONMENT="development").registration_enabled is True
    assert (
        Settings(ENVIRONMENT="development", REGISTRATION_ENABLED=False).registration_enabled
        is False
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "https://one.example, https://two.example",
            ["https://one.example", "https://two.example"],
        ),
        (
            json.dumps(["https://one.example", "https://two.example"]),
            ["https://one.example", "https://two.example"],
        ),
    ],
)
def test_trusted_origins_preserve_comma_and_json_cors_parsing(
    value: str, expected: list[str]
) -> None:
    settings = Settings(CORS_ORIGINS=value)

    assert settings.cors_origins_list == expected
    assert settings.trusted_origins == expected


def test_invalid_json_cors_origins_fails_closed() -> None:
    settings = Settings(CORS_ORIGINS="[")

    with pytest.raises(json.JSONDecodeError):
        _ = settings.trusted_origins


def test_empty_cors_origins_exposes_no_trusted_origins() -> None:
    settings = Settings(CORS_ORIGINS="")

    assert settings.trusted_origins == []


@pytest.mark.parametrize(
    "setting_name",
    [
        "SESSION_EXPIRE_MINUTES",
        "LOGIN_RATE_LIMIT",
        "LOGIN_RATE_LIMIT_WINDOW_SECONDS",
        "ADVISOR_RATE_LIMIT",
        "ADVISOR_RATE_LIMIT_WINDOW_SECONDS",
        "UPLOAD_RATE_LIMIT",
        "UPLOAD_RATE_LIMIT_WINDOW_SECONDS",
    ],
)
def test_security_time_and_rate_settings_must_be_positive(setting_name: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**{setting_name: 0})
