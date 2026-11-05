import gzip
import json
from dataclasses import replace

import httpx
import pytest

from app.openai_client import BoundedTransport
from tests.test_documents.test_receipt_read_payload import payload_data
from tests.test_documents.test_receipt_read_policy import config_settings
from tests.test_documents.test_vision_client import _response


def configuration():
    from app.documents.receipt_read_config import get_receipt_read_config

    return get_receipt_read_config(config_settings())


def fake_http(monkeypatch, handler):
    from app.documents import receipt_read_client

    monkeypatch.setattr(
        receipt_read_client,
        "_create_http_client",
        lambda config: httpx.AsyncClient(
            transport=BoundedTransport(
                httpx.MockTransport(handler), max_bytes=config.max_response_bytes
            ),
            timeout=config.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ),
    )


async def test_provider_is_one_bounded_no_retry_store_false_call(monkeypatch):
    from app.documents.receipt_read_client import extract_receipt_items

    calls = []

    def handler(req):
        calls.append(req)
        return _response(payload_data())

    fake_http(monkeypatch, handler)
    result = await extract_receipt_items(b"bounded-synthetic-jpeg", config=configuration())
    assert result.payload is not None and result.error_code is None and not result.uncertain
    assert len(calls) == 1
    request = json.loads(calls[0].content)
    assert request["store"] is False and request["model"] == "test-only-model"
    assert request["max_output_tokens"] == 8192 and "tools" not in request
    schema = request["text"]["format"]["schema"]
    assert (
        schema["additionalProperties"] is False and schema["properties"]["lines"]["maxItems"] == 200
    )
    assert "category_id" not in json.dumps(request) and "account_id" not in json.dumps(request)
    assert request["input"][1]["content"][0]["type"] == "input_image"


@pytest.mark.parametrize(
    "status,uncertain",
    [(400, False), (401, False), (403, False), (429, False), (500, True), (503, True)],
)
async def test_provider_errors_are_safe_and_never_retry(monkeypatch, caplog, status, uncertain):
    from app.documents.receipt_read_client import extract_receipt_items

    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(
            status, json={"error": {"message": "private-model-response", "type": "test"}}
        )

    fake_http(monkeypatch, handler)
    result = await extract_receipt_items(b"private-image-marker", config=configuration())
    assert result.payload is None and result.error_code and result.uncertain is uncertain
    assert len(calls) == 1
    for secret in ["private-model-response", "private-image-marker", "fake-never-sent"]:
        assert secret not in repr(result) + caplog.text


async def test_timeout_after_dispatch_is_uncertain_not_retryable(monkeypatch):
    from app.documents.receipt_read_client import extract_receipt_items

    calls = []

    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout("private timeout", request=req)

    fake_http(monkeypatch, handler)
    result = await extract_receipt_items(b"jpeg", config=configuration())
    assert result.uncertain and result.payload is None and len(calls) == 1


@pytest.mark.parametrize("kind", ["incomplete", "refusal", "bad_schema", "oversized_gzip"])
async def test_bad_or_truncated_output_is_not_silently_partial_success(monkeypatch, kind):
    from app.documents.receipt_read_client import extract_receipt_items

    def handler(req):
        if kind == "incomplete":
            return _response(payload_data(), finish_reason="length")
        if kind == "refusal":
            return _response({}, refusal="private refusal")
        if kind == "bad_schema":
            return _response({**payload_data(), "account_id": "injected"})
        return httpx.Response(
            200,
            content=gzip.compress(b"x" * 300000),
            headers={"content-encoding": "gzip", "content-type": "application/json"},
        )

    fake_http(monkeypatch, handler)
    result = await extract_receipt_items(b"jpeg", config=configuration())
    assert result.payload is None and result.error_code and not result.uncertain


async def test_unapproved_destination_is_rejected_before_credentials_or_bytes(monkeypatch):
    from app.documents.receipt_read_client import extract_receipt_items

    calls = []

    def handler(req):
        calls.append(req)
        return _response(payload_data())

    fake_http(monkeypatch, handler)
    result = await extract_receipt_items(
        b"jpeg", config=replace(configuration(), base_url="https://evil.invalid/v1")
    )
    assert result.payload is None and calls == []
