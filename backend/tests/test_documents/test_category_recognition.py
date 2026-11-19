"""Optional category context is one recognition call, never a second provider job."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.documents.vision_config import VisionConfig
from test_documents.test_vision_client import _payload, _response


@pytest.mark.parametrize("choice", ["c01", None, "foreign-key"])
@pytest.mark.asyncio
async def test_image_category_context_is_bounded_and_uses_one_call(monkeypatch, choice):
    from app.documents import vision_client

    requests = []

    async def handler(request):
        requests.append(json.loads(request.content))
        return _response(_payload(category_key=choice))

    monkeypatch.setattr(
        vision_client,
        "_create_http_client",
        lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    config = VisionConfig(
        "test", "https://vision.example.test/v1", "test-model", "synthetic", "p", "s"
    )
    result = await vision_client.extract_image_review(
        b"synthetic-jpeg",
        config=config,
        category_catalog=[{"key": "c01", "path": "Bills / Mobile"}],
    )
    assert result.category_key == ("c01" if choice == "c01" else None)
    assert result.ready
    assert len(requests) == 1
    assert "Bills / Mobile" in json.dumps(requests[0])
    assert requests[0]["store"] is False
    assert "tools" not in requests[0]
    schema = requests[0]["text"]["format"]["schema"]
    assert "category_key" in schema["required"]
    assert schema["properties"]["category_key"]["anyOf"][0]["enum"] == ["c01"]


@pytest.mark.asyncio
async def test_text_category_context_uses_same_strict_payload_without_extra_call(monkeypatch):
    from app.documents import extractor

    client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=object())),
        close=AsyncMock(),
    )
    monkeypatch.setattr(extractor, "_get_client", lambda: client)
    monkeypatch.setattr(extractor.settings, "DOCUMENT_TEXT_MODEL", "test-model")
    monkeypatch.setattr(
        extractor, "response_text", lambda response: json.dumps(_payload(category_key="c01"))
    )
    result = await extractor.extract_review_with_categories(
        "Synthetic printed document text",
        [{"key": "c01", "path": "Bills / Mobile"}],
    )
    assert result.suggestion.fields.total == "12.30"
    assert result.category_key == "c01"
    assert client.responses.create.await_count == 1
    request = client.responses.create.call_args.kwargs
    assert request["text"]["format"]["strict"] is True
    assert "Bills / Mobile" in json.dumps(request["input"])
    assert "Synthetic printed document text" in json.dumps(request["input"])


@pytest.mark.asyncio
async def test_manual_category_call_sends_only_saved_fields_and_allowed_category_keys(monkeypatch):
    from app.documents import extractor

    provider = AsyncMock(return_value=object())

    @asynccontextmanager
    async def client():
        yield SimpleNamespace(responses=SimpleNamespace(create=provider))

    monkeypatch.setattr(extractor, "_get_client", client)
    monkeypatch.setattr(extractor.settings, "DOCUMENT_TEXT_MODEL", "test-model")
    monkeypatch.setattr(extractor, "response_text", lambda _: '{"category_key":"c01"}')
    catalog = [{"key": "c01", "path": "Rachunki / Internet"}]

    result = await extractor.suggest_category_from_review(
        supplier="Dostawca", description="Internet domowy", catalog=catalog
    )

    assert result == "c01"
    provider.assert_awaited_once()
    request = provider.call_args.kwargs
    assert json.loads(request["input"][1]["content"]) == {
        "supplier": "Dostawca",
        "description": "Internet domowy",
        "categories": catalog,
    }
    assert request["store"] is False
    assert "tools" not in request
    format_ = request["text"]["format"]
    schema = format_["schema"]
    assert format_["strict"] is True
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["category_key"]
    assert schema["properties"]["category_key"]["anyOf"][0]["enum"] == ["c01"]


@pytest.mark.asyncio
async def test_legacy_documents_do_not_export_the_category_catalog():
    import uuid

    from app.documents.category_catalog import load_document_category_catalog

    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    )
    result = await load_document_category_catalog(db, uuid.uuid4(), uuid.uuid4())
    assert result.public == []
    assert db.execute.await_count == 1
