"""Purpose configuration must not inherit consent or become unreadable after a limit change."""

import pytest
from pydantic import ValidationError


@pytest.mark.parametrize(
    "values",
    [["2026-11-04T12:00:00+00:00", {}], [{}, "not-uuid"], ["2026-11-04T12:00:00+00:00", None]],
)
def test_malformed_cursor_objects_are_controlled_422(values):
    import base64
    import json

    from app.finance.categorization_context import CategorizationError
    from app.finance.receipt_read_service import _cursor

    with pytest.raises(CategorizationError) as error:
        _cursor(base64.urlsafe_b64encode(json.dumps(values).encode()).decode())
    assert error.value.status == 422


def test_operator_receipt_policy_requires_explicit_matching_target(monkeypatch):
    from scripts.receipt_read_policy import target_url

    s = config_settings()
    monkeypatch.delenv("RECEIPT_READ_POLICY_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="explicit"):
        target_url(s)
    monkeypatch.setenv("RECEIPT_READ_POLICY_DATABASE_URL", s.DATABASE_URL + "?options=evil")
    with pytest.raises(ValueError):
        target_url(s)
    monkeypatch.setenv("RECEIPT_READ_POLICY_DATABASE_URL", s.DATABASE_URL)
    assert target_url(s) == s.DATABASE_URL


def config_settings(**changes):
    from app.config import Settings

    values = {
        "ENVIRONMENT": "development",
        "DOCUMENT_RECEIPT_ITEMS_PROVIDER": "openai",
        "DOCUMENT_RECEIPT_ITEMS_BASE_URL": "https://api.openai.com/v1",
        "DOCUMENT_RECEIPT_ITEMS_MODEL": "test-only-model",
        "DOCUMENT_RECEIPT_ITEMS_API_KEY": "fake-never-sent",
        "DOCUMENT_RECEIPT_ITEMS_PROMPT_VERSION": "read-v1",
        "DOCUMENT_RECEIPT_ITEMS_SCHEMA_VERSION": "read-v1",
        **changes,
    }
    return Settings(_env_file=None, **values)


def test_receipt_read_config_does_not_inherit_header_activation():
    from app.config import Settings
    from app.documents.receipt_read_config import get_receipt_read_config

    s = Settings(
        _env_file=None,
        ENVIRONMENT="development",
        DOCUMENT_VISION_ENABLED=True,
        DOCUMENT_VISION_PROVIDER="openai",
        DOCUMENT_VISION_BASE_URL="https://api.openai.com/v1",
        DOCUMENT_VISION_MODEL="header-model",
        DOCUMENT_VISION_API_KEY="header-secret",
    )
    assert get_receipt_read_config(s) is None
    assert s.DOCUMENT_RECEIPT_ITEMS_ENABLED is False


def test_fingerprint_captures_intake_bounds_but_not_secret_or_quota():
    from app.documents.receipt_read_config import get_receipt_read_config

    first = get_receipt_read_config(config_settings())
    assert first is not None
    assert "fake-never-sent" not in repr(first)
    second = get_receipt_read_config(
        config_settings(
            DOCUMENT_RECEIPT_ITEMS_API_KEY="other-secret",
            DOCUMENT_RECEIPT_ITEMS_DAILY_CALL_LIMIT_PER_USER=1,
        )
    )
    assert first.configuration_fingerprint == second.configuration_fingerprint
    changed = get_receipt_read_config(config_settings(FINANCE_RECEIPT_MAX_LINES=100))
    assert changed.configuration_fingerprint != first.configuration_fingerprint
    assert first.max_lines == 200 and changed.max_lines == 100


@pytest.mark.parametrize(
    "url",
    [
        "http://api.openai.com/v1",
        "https://api.openai.com.evil.invalid/v1",
        "https://user@api.openai.com/v1",
        "https://api.openai.com/v1?secret=x",
        "https://elsewhere.invalid/v1",
    ],
)
def test_receipt_read_rejects_unapproved_destination(url):
    from app.documents.receipt_read_config import get_receipt_read_config

    assert get_receipt_read_config(config_settings(DOCUMENT_RECEIPT_ITEMS_BASE_URL=url)) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"DOCUMENT_RECEIPT_ITEMS_LEASE_SECONDS": 100},
        {"DOCUMENT_RECEIPT_ITEMS_MAX_EDGE": 9000},
        {"DOCUMENT_RECEIPT_ITEMS_MAX_BYTES": 20971521},
        {"DOCUMENT_RECEIPT_ITEMS_MAX_PIXELS": 25000001},
        {"DOCUMENT_RECEIPT_ITEMS_DAILY_CALL_LIMIT_PER_USER": 101},
        {"DOCUMENT_RECEIPT_ITEMS_QUEUE_LIMIT_PER_USER": 101},
        {"DOCUMENT_RECEIPT_ITEMS_CONCURRENCY": 0},
    ],
)
def test_receipt_read_safety_caps_and_lease_rejected(changes):
    with pytest.raises(ValidationError):
        config_settings(**changes)


@pytest.mark.parametrize("confirmed", [1, False, "true"])
def test_start_requires_actual_true_and_rejects_client_authority(confirmed):
    import uuid

    from app.documents.receipt_read_schemas import ReceiptReadStart

    with pytest.raises(ValidationError):
        ReceiptReadStart(
            document_id=uuid.uuid4(), expected_export_snapshot="a" * 64, confirmed=confirmed
        )
    with pytest.raises(ValidationError):
        ReceiptReadStart(
            document_id=uuid.uuid4(),
            expected_export_snapshot="a" * 64,
            confirmed=True,
            model="client-selected",
        )
