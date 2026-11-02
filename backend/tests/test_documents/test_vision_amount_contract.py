"""The outbound amount grammar must match the exact financial review boundary."""

import json
import re
import traceback

import httpx
import pytest
from pydantic import ValidationError

from app.documents import vision_client
from app.documents.vision_schemas import VisionPayload, to_minor_units
from test_documents.test_vision_client import _config, _payload, _response

VALID_TOTALS = [
    ("1", 100),
    ("1.2", 120),
    ("12.30", 1230),
    ("1234.56", 123456),
    ("0.01", 1),
    ("0.1", 10),
    ("0.10", 10),
    ("90071992547409.91", 9_007_199_254_740_991),
]
INVALID_STRINGS = [
    "1234,56",
    "1 234.56",
    "1\u00a0234.56",
    "1\u202f234.56",
    "1,234.56",
    "1.234,56",
    "1234.56 PLN",
    "+1.00",
    "-1.00",
    "0",
    "0.0",
    "0.00",
    "00.10",
    ".50",
    "1.",
    " 1.00",
    "1.00 ",
    "1.00\n",
    "1.230",
    "1e2",
    "1E+2",
    "NaN",
    "Infinity",
    "１２.３０",
    "",
    "SYNTHETIC_PRIVATE_AMOUNT",
]


@pytest.mark.parametrize("requirement", ["optional decimal point", "ambiguous separators"])
async def test_outbound_schema_and_instructions_constrain_total(
    monkeypatch: pytest.MonkeyPatch,
    requirement: str,
) -> None:
    """Dropping the grammar would again permit arbitrary text in a strict AI response."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _response(_payload())

    monkeypatch.setattr(
        vision_client,
        "_create_http_client",
        lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs),
    )
    await vision_client.extract_image_review(b"synthetic", config=_config())
    assert len(requests) == 1
    body = json.loads(requests[0].content)
    assert body["text"]["format"]["strict"] is True
    total = body["text"]["format"]["schema"]["$defs"]["VisionFields"]["properties"]["total"]
    assert {"type": "null"} in total["anyOf"]
    string_schema = next(item for item in total["anyOf"] if item["type"] == "string")
    for value, _ in VALID_TOTALS:
        assert re.fullmatch(string_schema["pattern"], value) is not None
    for value in INVALID_STRINGS:
        assert re.fullmatch(string_schema["pattern"], value) is None
    assert "decimal" in total["description"] and "null" in total["description"]
    assert requirement in total["description"]
    instructions = body["input"][0]["content"]
    assert requirement in instructions
    for fragment in ("total", "1234.56", "decimal point", "null", "round"):
        assert fragment in instructions
    assert body["store"] is False and "tools" not in body


@pytest.mark.parametrize("total", INVALID_STRINGS)
def test_model_facing_schema_rejects_noncanonical_or_nonpositive_total(total: str) -> None:
    """Validation must not silently repair localized, ambiguous or unsafe amounts."""
    with pytest.raises(ValidationError):
        VisionPayload.model_validate_json(
            json.dumps(_payload(fields={**_payload()["fields"], "total": total}))
        )


@pytest.mark.parametrize(("total", "minor"), VALID_TOTALS)
async def test_canonical_total_is_preserved_with_exact_minor_units(
    monkeypatch: pytest.MonkeyPatch, total: str, minor: int
) -> None:
    """Rejecting small positive amounts or using floats would change the stored value."""
    monkeypatch.setattr(
        vision_client,
        "_create_http_client",
        lambda **kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: _response(_payload(fields={**_payload()["fields"], "total": total}))
            ),
            **kwargs,
        ),
    )
    result = await vision_client.extract_image_review(b"synthetic", config=_config())
    assert result.ready is True
    assert result.suggestion.fields.total == total
    assert to_minor_units(result.suggestion.fields.total) == minor


async def test_unknown_total_remains_null_and_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing amount must not become a zero, a guess or a ready review."""
    monkeypatch.setattr(
        vision_client,
        "_create_http_client",
        lambda **kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: _response(_payload(fields={**_payload()["fields"], "total": None}))
            ),
            **kwargs,
        ),
    )
    result = await vision_client.extract_image_review(b"synthetic", config=_config())
    assert result.suggestion.fields.total is None
    assert result.ready is False
    assert "missing_required_fields" in result.warnings


@pytest.mark.parametrize("total", [*INVALID_STRINGS, "90071992547409.92", 12.3, 1234, True])
async def test_invalid_total_fails_once_without_input_or_traceback_leaks(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, total: object
) -> None:
    """Even a provider ignoring the schema cannot bypass limits or trigger a retry."""
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response(_payload(fields={**_payload()["fields"], "total": total}))

    monkeypatch.setattr(
        vision_client,
        "_create_http_client",
        lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs),
    )
    image = b"synthetic-private-image"
    with pytest.raises(vision_client.VisionProviderError) as raised:
        await vision_client.extract_image_review(image, config=_config())
    assert (raised.value.code, raised.value.retryable, calls) == ("invalid_model_output", False, 1)
    rendered = "".join(traceback.format_exception(raised.value))
    for marker in (
        "SYNTHETIC_PRIVATE_AMOUNT",
        "synthetic-private-image",
        "marker-secret",
        "Example Shop",
    ):
        assert marker not in caplog.text and marker not in rendered
    assert all(record.exc_info is None for record in caplog.records)
