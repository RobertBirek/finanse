"""Shared Responses client fails closed and never delegates transport policy to the SDK."""

import gzip
import json
from types import SimpleNamespace

import httpx
import pytest

from app import openai_client
from app.openai_client import ResponseOutputError, create_openai_client, response_text


def _response(*, status: str = "completed", output: list[object]) -> SimpleNamespace:
    return SimpleNamespace(status=status, output=output)


def test_response_text_returns_completed_output_text() -> None:
    """Returning an empty string for a completed text response would hide valid model output."""
    response = _response(
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="output_text", text="Gotowa odpowiedź")],
            )
        ]
    )

    assert response_text(response) == "Gotowa odpowiedź"


@pytest.mark.parametrize(
    "response",
    [
        _response(status="incomplete", output=[]),
        _response(status="failed", output=[]),
        _response(
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="refusal", refusal="no")],
                )
            ]
        ),
        _response(output=[SimpleNamespace(type="function_call", name="get_accounts")]),
        _response(output=[]),
    ],
)
def test_response_text_rejects_non_final_or_non_text_output(response: SimpleNamespace) -> None:
    """Accepting incomplete/refused output would publish a model result that was never completed."""
    with pytest.raises(ResponseOutputError):
        response_text(response)


@pytest.mark.asyncio
async def test_client_posts_responses_request_with_flat_non_strict_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nesting tool fields or using Chat Completions would break the Responses tool contract."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "response-test",
                "object": "response",
                "created_at": 0,
                "model": "gpt-test",
                "status": "completed",
                "output": [],
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
            },
        )

    monkeypatch.setattr(
        openai_client.httpx,
        "AsyncHTTPTransport",
        lambda retries: httpx.MockTransport(handler),
    )
    client = create_openai_client(
        api_key="test-key", base_url="https://api.openai.com/v1", timeout=5
    )
    try:
        await client.responses.create(
            model="gpt-test",
            input=[{"role": "user", "content": "Pokaż konta"}],
            tools=[
                {
                    "type": "function",
                    "name": "get_accounts",
                    "description": "Lista kont",
                    "parameters": {"type": "object", "properties": {}},
                    "strict": False,
                }
            ],
            store=False,
        )
    finally:
        await client.close()

    body = json.loads(requests[0].content)
    assert (requests[0].method, requests[0].url.path, body["store"]) == (
        "POST",
        "/v1/responses",
        False,
    )
    assert body["tools"] == [
        {
            "type": "function",
            "name": "get_accounts",
            "description": "Lista kont",
            "parameters": {"type": "object", "properties": {}},
            "strict": False,
        }
    ]
    assert not {"messages", "temperature", "max_tokens", "response_format"} & body.keys()


def test_client_rejects_stale_deepseek_target_before_transport_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sending an OpenAI credential to a stale DeepSeek endpoint is a credential leak."""
    created = False

    def unexpected_client(*, timeout: float) -> httpx.AsyncClient:
        nonlocal created
        created = True
        return httpx.AsyncClient()

    monkeypatch.setattr(openai_client, "create_http_client", unexpected_client)
    with pytest.raises(ValueError):
        create_openai_client(
            api_key="openai-secret", base_url="https://api.deepseek.com", timeout=5
        )
    assert created is False


@pytest.mark.asyncio
@pytest.mark.parametrize("compressed", [False, True])
async def test_client_parses_bounded_responses_body_when_upstream_is_encoded(
    monkeypatch: pytest.MonkeyPatch, compressed: bool
) -> None:
    """Retaining gzip headers after buffering decoded bytes would double-decompress provider output."""
    payload = json.dumps(
        {
            "id": "response-test",
            "object": "response",
            "created_at": 0,
            "model": "gpt-test",
            "status": "completed",
            "output": [
                {
                    "id": "message-test",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "OK"}],
                }
            ],
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
        }
    ).encode()

    async def handler(_request: httpx.Request) -> httpx.Response:
        body = gzip.compress(payload) if compressed else payload
        headers = {"content-type": "application/json", "content-length": str(len(body))}
        if compressed:
            headers["content-encoding"] = "gzip"
        return httpx.Response(200, content=body, headers=headers)

    monkeypatch.setattr(
        openai_client,
        "create_http_client",
        lambda *, timeout: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=timeout
        ),
    )
    client = create_openai_client(
        api_key="test-key", base_url="https://api.openai.com/v1", timeout=5
    )
    try:
        response = await client.responses.create(
            model="gpt-test", input=[{"role": "user", "content": "test"}], store=False
        )
    finally:
        await client.close()

    assert response_text(response) == "OK"
