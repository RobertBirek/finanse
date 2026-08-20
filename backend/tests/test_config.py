import json

import pytest
from pydantic import ValidationError

from app.config import Settings

TASK2_ENVIRONMENT_VARIABLES = (
    "TRUSTED_ORIGINS",
    "CORS_ORIGINS",
    "ENVIRONMENT",
    "REGISTRATION_ENABLED",
    "SESSION_EXPIRE_MINUTES",
    "LOGIN_RATE_LIMIT",
    "LOGIN_RATE_LIMIT_WINDOW_SECONDS",
    "ADVISOR_RATE_LIMIT",
    "ADVISOR_RATE_LIMIT_WINDOW_SECONDS",
    "UPLOAD_RATE_LIMIT",
    "UPLOAD_RATE_LIMIT_WINDOW_SECONDS",
    "TRUSTED_PROXY_HOSTS",
    "SECRET_KEY",
)


@pytest.fixture
def make_settings(monkeypatch):
    def factory(*, environment: dict[str, str] | None = None, **values: object) -> Settings:
        for variable in TASK2_ENVIRONMENT_VARIABLES:
            monkeypatch.delenv(variable, raising=False)
        for variable, value in (environment or {}).items():
            monkeypatch.setenv(variable, value)
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
            TRUSTED_ORIGINS="https://app.example",
        )


def test_production_accepts_a_distinct_32_character_secret(make_settings) -> None:
    settings = make_settings(
        ENVIRONMENT="production", SECRET_KEY="s" * 32, TRUSTED_ORIGINS="https://app.example"
    )

    assert settings.SECRET_KEY == "s" * 32


def test_production_requires_at_least_one_trusted_proxy_host(make_settings) -> None:
    with pytest.raises(ValidationError, match="TRUSTED_PROXY_HOSTS"):
        make_settings(
            ENVIRONMENT="production",
            SECRET_KEY="s" * 32,
            TRUSTED_ORIGINS="https://app.example",
            TRUSTED_PROXY_HOSTS="",
        )


def test_production_always_disables_registration(make_settings) -> None:
    settings = make_settings(
        ENVIRONMENT="production",
        SECRET_KEY="s" * 32,
        REGISTRATION_ENABLED=True,
        TRUSTED_ORIGINS="https://app.example",
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

    assert settings.trusted_origins == tuple(expected)
    assert settings.cors_origins_list == expected


def test_trusted_origins_accept_comma_separated_and_json_settings(make_settings) -> None:
    comma_settings = make_settings(TRUSTED_ORIGINS=" HTTPS://App.Example:8443,https://two.example")
    json_settings = make_settings(TRUSTED_ORIGINS=json.dumps(["https://one.example"]))

    assert comma_settings.trusted_origins == ("https://app.example:8443", "https://two.example")
    assert json_settings.trusted_origins == ("https://one.example",)


@pytest.mark.parametrize(
    "value",
    [
        "https://one.example,https://two.example",
        '["https://one.example","https://two.example"]',
    ],
)
def test_trusted_origins_environment_accepts_comma_and_json_forms(
    make_settings, value: str
) -> None:
    settings = make_settings(environment={"TRUSTED_ORIGINS": value})

    assert settings.trusted_origins == ("https://one.example", "https://two.example")


def test_localhost_and_valid_ip_literals_are_trusted_origins(make_settings) -> None:
    settings = make_settings(
        TRUSTED_ORIGINS="http://localhost,https://127.0.0.1:8443,https://[::1]"
    )

    assert settings.trusted_origins == (
        "http://localhost",
        "https://127.0.0.1:8443",
        "https://[::1]",
    )


def test_explicit_constructor_legacy_cors_origins_override_ambient_trusted_origins(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TRUSTED_ORIGINS", "https://ambient.example")

    settings = Settings(_env_file=None, CORS_ORIGINS="https://legacy.example")

    assert settings.trusted_origins == ("https://legacy.example",)


def test_explicit_constructor_trusted_origins_override_ambient_trusted_origins(monkeypatch) -> None:
    monkeypatch.setenv("TRUSTED_ORIGINS", "https://ambient.example")

    settings = Settings(
        _env_file=None,
        CORS_ORIGINS="https://legacy.example",
        TRUSTED_ORIGINS="https://explicit.example",
    )

    assert settings.trusted_origins == ("https://explicit.example",)


def test_runtime_trusted_origins_override_runtime_legacy_cors_origins(monkeypatch) -> None:
    monkeypatch.setenv("TRUSTED_ORIGINS", "https://canonical.example")
    monkeypatch.setenv("CORS_ORIGINS", "https://legacy.example")

    settings = Settings(_env_file=None)

    assert settings.trusted_origins == ("https://canonical.example",)


@pytest.mark.parametrize(
    "values",
    [
        {"CORS_ORIGINS": ""},
        {"CORS_ORIGINS": "[]"},
        {"CORS_ORIGINS": "["},
        {"CORS_ORIGINS": '{"origin":"https://app.example"}'},
        {"TRUSTED_ORIGINS": "[]"},
        {"TRUSTED_ORIGINS": ""},
        {"TRUSTED_ORIGINS": "https://app.example,https://APP.example"},
        {"TRUSTED_ORIGINS": "ftp://app.example"},
        {"TRUSTED_ORIGINS": "https://"},
        {"TRUSTED_ORIGINS": "https://app.example/path"},
        {"TRUSTED_ORIGINS": "https://app.example?query=true"},
        {"TRUSTED_ORIGINS": "https://app.example#fragment"},
        {"TRUSTED_ORIGINS": "https://user@app.example"},
        {"TRUSTED_ORIGINS": "https://app.example:0"},
        {"TRUSTED_ORIGINS": "https://app.example:65536"},
        {"TRUSTED_ORIGINS": "https://app%2eexample"},
        {"TRUSTED_ORIGINS": "https://app.example\\path"},
        {"TRUSTED_ORIGINS": "https://-app.example"},
        {"TRUSTED_ORIGINS": "https://999.999.999.999"},
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
            TRUSTED_ORIGINS="http://app.example",
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
