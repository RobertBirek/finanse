import json

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture
def make_settings():
    def factory(**values: object) -> Settings:
        return Settings(_env_file=None, **values)

    return factory


@pytest.mark.parametrize(
    "secret_key",
    ["", "change-me-in-production-use-a-real-secret-key", "x" * 31],
)
def test_production_requires_a_strong_non_placeholder_secret(
    make_settings, secret_key: str
) -> None:
    with pytest.raises(ValidationError):
        make_settings(
            ENVIRONMENT="production",
            SECRET_KEY=secret_key,
            TRUSTED_ORIGINS=["https://app.example"],
        )


def test_production_accepts_a_distinct_32_character_secret(make_settings) -> None:
    settings = make_settings(
        ENVIRONMENT="production", SECRET_KEY="s" * 32, TRUSTED_ORIGINS=["https://app.example"]
    )

    assert settings.SECRET_KEY == "s" * 32


def test_production_always_disables_registration(make_settings) -> None:
    settings = make_settings(
        ENVIRONMENT="production",
        SECRET_KEY="s" * 32,
        REGISTRATION_ENABLED=True,
        TRUSTED_ORIGINS=["https://app.example"],
    )

    assert settings.registration_enabled is False


def test_development_registration_defaults_to_enabled_and_can_be_disabled(make_settings) -> None:
    assert make_settings(ENVIRONMENT="development").registration_enabled is True
    assert (
        make_settings(ENVIRONMENT="development", REGISTRATION_ENABLED=False).registration_enabled
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
def test_legacy_cors_origins_populate_the_typed_trusted_allowlist(
    make_settings, value: str, expected: list[str]
) -> None:
    settings = make_settings(CORS_ORIGINS=value)

    assert settings.TRUSTED_ORIGINS == expected
    assert settings.cors_origins_list == settings.TRUSTED_ORIGINS


def test_typed_trusted_origins_are_normalized(make_settings) -> None:
    settings = make_settings(TRUSTED_ORIGINS=[" HTTPS://App.Example:8443 "])

    assert settings.TRUSTED_ORIGINS == ["https://app.example:8443"]


@pytest.mark.parametrize(
    "values",
    [
        {"CORS_ORIGINS": ""},
        {"CORS_ORIGINS": "[]"},
        {"CORS_ORIGINS": "["},
        {"CORS_ORIGINS": '{"origin":"https://app.example"}'},
        {"TRUSTED_ORIGINS": []},
        {"TRUSTED_ORIGINS": [""]},
        {"TRUSTED_ORIGINS": ["https://app.example", "https://APP.example"]},
        {"TRUSTED_ORIGINS": ["ftp://app.example"]},
        {"TRUSTED_ORIGINS": ["https://"]},
        {"TRUSTED_ORIGINS": ["https://app.example/path"]},
        {"TRUSTED_ORIGINS": ["https://app.example?query=true"]},
        {"TRUSTED_ORIGINS": ["https://app.example#fragment"]},
        {"TRUSTED_ORIGINS": ["https://user@app.example"]},
    ],
)
def test_unsafe_trusted_origin_configuration_fails_during_construction(
    make_settings, values
) -> None:
    with pytest.raises(ValidationError):
        make_settings(**values)


def test_production_requires_https_trusted_origins(make_settings) -> None:
    with pytest.raises(ValidationError):
        make_settings(
            ENVIRONMENT="production",
            SECRET_KEY="s" * 32,
            TRUSTED_ORIGINS=["http://app.example"],
        )


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
def test_security_time_and_rate_settings_must_be_positive(make_settings, setting_name: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{setting_name: 0})
