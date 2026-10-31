"""The image adapter sends only a bounded, strict vision request."""

import base64
import json

import httpx
import pytest

from app.documents.vision_config import VisionConfig


def _config() -> VisionConfig:
    return VisionConfig(
        provider="test-provider",
        base_url="https://vision.example.test/v1",
        model="test-vision-model",
        api_key="marker-secret",
        prompt_version="vision-prompt-1",
        schema_version="vision-schema-1",
    )


def _payload(**overrides: object) -> dict[str, object]:
    fields = {
        "supplier_name": "Example Shop",
        "supplier_tax_id": None,
        "number": None,
        "issue_date": None,
        "sale_date": None,
        "due_date": None,
        "description": "Groceries",
        "payee_iban": None,
        "total": "12.30",
        "currency": "EUR",
    }
    return {"document_type": "receipt", "fields": fields, "warnings": [], **overrides}


def _response(payload: object, *, status_code: int = 200) -> httpx.Response:
    content = json.dumps(
        {
            "id": "test",
            "object": "chat.completion",
            "created": 0,
            "model": "test-vision-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": json.dumps(payload)},
                }
            ],
        }
    )
    return httpx.Response(
        status_code, content=content, headers={"content-type": "application/json"}
    )


async def test_vision_reads_image_without_ocr_text_and_uses_strict_schema(
    monkeypatch: pytest.MonkeyPatch,
):
    """Removing image-only schema fields or adding document metadata breaks this contract."""
    from app.documents import vision_client

    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _response(_payload())

    monkeypatch.setattr(
        vision_client,
        "_create_http_client",
        lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs),
    )

    extraction = await vision_client.extract_image_review(b"jpeg-bytes", config=_config())

    assert extraction.ready is True
    assert extraction.suggestion.provenance == {"source": "vision"}
    assert extraction.suggestion.parser_version == "test-provider:test-vision-model"
    assert len(requests) == 1
    body = json.loads(requests[0].content)
    assert body["model"] == "test-vision-model"
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1]["content"][0]["image_url"]["url"] == (
        "data:image/jpeg;base64," + base64.b64encode(b"jpeg-bytes").decode("ascii")
    )
    assert "filename" not in json.dumps(body)
    assert "account_id" not in json.dumps(body)
    assert "tools" not in body
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"document_type", "fields", "warnings"}
    field_schema = schema["$defs"]["VisionFields"]
    assert set(field_schema["required"]) == set(_payload()["fields"])
    assert field_schema["additionalProperties"] is False


@pytest.mark.parametrize(
    "payload, code",
    [
        ({"document_type": "receipt", "fields": _payload()["fields"]}, "invalid_model_output"),
        (_payload(provenance={"total": "prompt injection"}), "invalid_model_output"),
        (_payload(fields={**_payload()["fields"], "total": "1e2"}), "invalid_model_output"),
        (
            _payload(fields={**_payload()["fields"], "total": "90071992547409.92"}),
            "invalid_model_output",
        ),
    ],
)
async def test_invalid_or_nonreviewable_vision_output_fails_closed_once(
    monkeypatch: pytest.MonkeyPatch, payload: object, code: str
):
    """Removing validation of a malformed value must not yield a ready suggestion."""
    from app.documents import vision_client

    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response(payload)

    monkeypatch.setattr(
        vision_client,
        "_create_http_client",
        lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs),
    )

    with pytest.raises(vision_client.VisionProviderError) as raised:
        await vision_client.extract_image_review(b"jpeg", config=_config())

    assert raised.value.code == code
    assert raised.value.retryable is False
    assert calls == 1


async def test_rate_limit_is_retryable_without_sdk_retry(monkeypatch: pytest.MonkeyPatch):
    """Enabling SDK retries would send a private image more than once."""
    from app.documents import vision_client

    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, content=b"bounded error")

    monkeypatch.setattr(
        vision_client,
        "_create_http_client",
        lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs),
    )
    with pytest.raises(vision_client.VisionProviderError) as raised:
        await vision_client.extract_image_review(b"jpeg", config=_config())
    assert (raised.value.code, raised.value.retryable, calls) == ("provider_unavailable", True, 1)


@pytest.mark.parametrize(
    "payload, warning",
    [
        (_payload(warnings=["unreadable"]), "unreadable"),
        (_payload(document_type="statement"), "unsupported_document"),
    ],
)
async def test_unreadable_or_nonfinancial_document_is_incomplete_not_reinterpreted(
    monkeypatch: pytest.MonkeyPatch, payload: object, warning: str
):
    """Treating a statement or unreadable image as a ready receipt would be unsafe."""
    from app.documents import vision_client

    async def handler(request: httpx.Request) -> httpx.Response:
        return _response(payload)

    monkeypatch.setattr(
        vision_client,
        "_create_http_client",
        lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs),
    )
    extraction = await vision_client.extract_image_review(b"jpeg", config=_config())
    assert extraction.ready is False
    assert warning in extraction.warnings


async def test_receipt_missing_iban_and_due_date_can_be_ready(monkeypatch: pytest.MonkeyPatch):
    """Changing readiness to require invoice-only fields breaks receipt review."""
    from app.documents import vision_client

    async def handler(request: httpx.Request) -> httpx.Response:
        return _response(_payload())

    monkeypatch.setattr(
        vision_client,
        "_create_http_client",
        lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs),
    )
    extraction = await vision_client.extract_image_review(b"jpeg", config=_config())
    assert extraction.ready is True


async def test_missing_required_value_and_null_currency_remain_incomplete(
    monkeypatch: pytest.MonkeyPatch,
):
    """Defaulting a missing currency or supplier would turn an unsafe draft into ready data."""
    from app.documents import vision_client

    async def handler(request: httpx.Request) -> httpx.Response:
        return _response(_payload(fields={**_payload()["fields"], "supplier_name": ""}))

    monkeypatch.setattr(
        vision_client,
        "_create_http_client",
        lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs),
    )
    extraction = await vision_client.extract_image_review(b"jpeg", config=_config())
    assert extraction.ready is False
    assert "missing_required_fields" in extraction.warnings
    assert extraction.suggestion.fields.currency == "EUR"
    assert extraction.suggestion.fields.issue_date is None


@pytest.mark.parametrize("total", ["1e2", "90071992547409.92"])
def test_minor_units_rejects_noncanonical_and_overflow_totals(total: str):
    """Replacing Decimal validation with float conversion would accept unsafe amounts."""
    from app.documents.vision_schemas import to_minor_units

    with pytest.raises(ValueError, match="invalid_amount"):
        to_minor_units(total)


async def test_provider_redirect_and_secret_are_not_followed_or_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Following a redirect or logging provider details would expose a private image."""
    from app.documents import vision_client

    seen_follow_redirects: list[bool] = []

    def client(**kwargs: object) -> httpx.AsyncClient:
        seen_follow_redirects.append(kwargs["follow_redirects"])
        return httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(307, headers={"location": "x"})
            ),
            **kwargs,
        )

    monkeypatch.setattr(vision_client, "_create_http_client", client)
    with pytest.raises(vision_client.VisionProviderError) as raised:
        await vision_client.extract_image_review(b"jpeg", config=_config())

    assert raised.value.code == "provider_unavailable"
    assert seen_follow_redirects == [False]
    assert "marker-secret" not in caplog.text
    assert "jpeg" not in caplog.text
