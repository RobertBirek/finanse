"""Untrusted LLM JSON must be validated before any financial suggestion is stored."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents import extractor
from app.documents.schemas import DocumentFinancialData

VALID = {
    "detected": True,
    "type": "expense",
    "amount": 12345,
    "currency": "PLN",
    "description": "Receipt",
    "date": "2026-10-20",
    "category_suggestion": "Food",
}
INVALID_FIELDS = [
    {"detected": "true"}, {"detected": "false"}, {"detected": 1}, {"detected": 0},
    {"amount": "12345"}, {"amount": True}, {"amount": 123.45}, {"amount": 12345.0},
    {"amount": 0}, {"amount": -1}, {"amount": 2**63},
    {"amount": float("nan")}, {"amount": float("inf")},
    {"currency": "GBP"}, {"currency": None}, {"currency": "pln"},
    {"type": "transfer"}, {"type": "exchange"},
    {"description": "   "}, {"description": {}}, {"description": "a" * 2001},
    {"date": "2026-02-30"}, {"date": "20261020"}, {"date": "2026-10-20T10:00:00Z"},
    {"date": 1792454400}, {"date": True},
    {"category_suggestion": {}}, {"category_suggestion": "a" * 201},
    {"sql": "SELECT 1"}, {"account_id": str(uuid.uuid4())},
]


@pytest.fixture
def provider(monkeypatch):
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock())),
        close=AsyncMock(),
    )
    monkeypatch.setattr(extractor, "_get_client", lambda: client)
    return client


def output(provider, content):
    provider.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.mark.parametrize("changed", INVALID_FIELDS)
async def test_invalid_model_fields_fail_closed(provider, changed):
    output(provider, json.dumps({**VALID, **changed}))
    assert await extractor.extract_financial_data("OCR text") == {"detected": False}
    provider.close.assert_awaited_once()


@pytest.mark.parametrize("raw", ["[]", "null", "true", "123", '"text"', "{}", "not JSON", "{", None, ""])
async def test_non_object_or_incomplete_output_has_no_detection(provider, raw):
    output(provider, raw)
    assert await extractor.extract_financial_data("OCR text") == {"detected": False}
    provider.close.assert_awaited_once()


@pytest.mark.parametrize("missing", ["detected", "type", "amount", "currency", "description"])
async def test_missing_required_financial_fields_are_not_invented(provider, missing):
    output(provider, json.dumps({key: value for key, value in VALID.items() if key != missing}))
    assert await extractor.extract_financial_data("OCR text") == {"detected": False}


@pytest.mark.parametrize("currency", ["PLN", "EUR", "USD"])
async def test_valid_output_is_normalized_and_remains_only_a_suggestion(provider, currency):
    output(provider, json.dumps({**VALID, "currency": currency, "description": "  Receipt  "}))
    assert await extractor.extract_financial_data("OCR text") == {**VALID, "currency": currency}
    provider.close.assert_awaited_once()


async def test_unknown_date_and_category_are_not_guessed(provider):
    data = {key: value for key, value in VALID.items() if key not in {"date", "category_suggestion"}}
    output(provider, json.dumps(data))
    assert await extractor.extract_financial_data("OCR text") == {
        **data, "date": None, "category_suggestion": None,
    }


async def test_negative_detection_is_supported(provider):
    output(provider, '{"detected":false}')
    assert await extractor.extract_financial_data("OCR text") == {"detected": False}


async def test_empty_choices_do_not_raise(provider):
    provider.chat.completions.create.return_value = SimpleNamespace(choices=[])
    assert await extractor.extract_financial_data("OCR text") == {"detected": False}
    provider.close.assert_awaited_once()


async def test_provider_exception_propagates_but_client_is_closed(provider):
    provider.chat.completions.create.side_effect = RuntimeError("Provider unavailable")
    with pytest.raises(RuntimeError, match="Provider unavailable"):
        await extractor.extract_financial_data("OCR text")
    provider.close.assert_awaited_once()


async def test_request_keeps_json_mode_and_limits_untrusted_text(provider):
    output(provider, '{"detected":false}')
    await extractor.extract_financial_data("x" * 9000)
    kwargs = provider.chat.completions.create.await_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["messages"][1] == {"role": "user", "content": "x" * 8000}
    assert kwargs["model"] == extractor.settings.LLM_MODEL


async def test_rejected_payload_is_not_logged(provider, caplog):
    output(provider, json.dumps({**VALID, "amount": "PRIVATE_MODEL_OUTPUT"}))
    assert await extractor.extract_financial_data("PRIVATE_OCR_TEXT") == {"detected": False}
    assert "PRIVATE_MODEL_OUTPUT" not in caplog.text
    assert "PRIVATE_OCR_TEXT" not in caplog.text
    assert "did not match the schema" in caplog.text


@pytest.mark.parametrize("changed", INVALID_FIELDS + [{"detected": False}])
async def test_invalid_suggestions_are_rejected_before_database_access(changed):
    db = AsyncMock(spec=AsyncSession)
    with pytest.raises(ValidationError):
        await extractor.create_inbox_from_document(
            db, uuid.uuid4(), uuid.uuid4(), "receipt.pdf", {**VALID, **changed}
        )
    db.execute.assert_not_awaited()
    db.add.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.parametrize("amount", [1, 9223372036854775807])
@pytest.mark.integration
async def test_valid_suggestion_persists_exact_minor_units_and_json_date(db_session, amount):
    from app.inbox.service import get_inbox_item

    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    data = {**VALID, "amount": amount, "currency": "EUR"}
    item = await extractor.create_inbox_from_document(
        db_session, user_id, document_id, "receipt.pdf", data
    )
    item_id = item.id
    await db_session.commit()
    db_session.expire_all()
    persisted = await get_inbox_item(db_session, user_id, item_id)
    assert persisted.agent_suggestion["extracted"] == data
    assert f"{amount // 100}.{amount % 100:02d} EUR" in persisted.content
    assert persisted.target_type == "transaction" and persisted.target_id is None
    assert persisted.is_processed is False
    assert DocumentFinancialData.model_validate(persisted.agent_suggestion["extracted"])
