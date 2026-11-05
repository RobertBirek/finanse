"""Small, fail-closed Responses client shared by application AI adapters."""

from collections.abc import AsyncIterator
from typing import cast
from urllib.parse import urlsplit

import httpx
from openai import AsyncOpenAI
from openai.types.responses import Response

_MAX_RESPONSE_BYTES = 1024 * 1024


class ResponseOutputError(ValueError):
    """A completed response did not contain safe, usable text output."""


class ResponseTooLarge(httpx.TransportError):
    """The provider sent a response larger than the application boundary."""


class BoundedTransport(httpx.AsyncBaseTransport):
    def __init__(self, transport: httpx.AsyncBaseTransport, *, max_bytes: int) -> None:
        self._transport = transport
        self._max_bytes = max_bytes

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._transport.handle_async_request(request)
        chunks: list[bytes] = []
        size = 0
        try:
            async for chunk in cast(AsyncIterator[bytes], response.aiter_bytes()):
                size += len(chunk)
                if size > self._max_bytes:
                    raise ResponseTooLarge("response exceeds limit")
                chunks.append(chunk)
        finally:
            await response.aclose()
        headers = httpx.Headers(response.headers)
        for header in ("content-encoding", "content-length", "transfer-encoding"):
            headers.pop(header, None)
        return httpx.Response(
            response.status_code,
            headers=headers,
            content=b"".join(chunks),
            request=request,
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._transport.aclose()


def create_http_client(
    *, timeout: float, max_response_bytes: int = _MAX_RESPONSE_BYTES
) -> httpx.AsyncClient:
    if not 0 < max_response_bytes <= _MAX_RESPONSE_BYTES:
        raise ValueError("Invalid response byte bound")
    return httpx.AsyncClient(
        transport=BoundedTransport(
            httpx.AsyncHTTPTransport(retries=0), max_bytes=max_response_bytes
        ),
        timeout=httpx.Timeout(timeout),
        follow_redirects=False,
        trust_env=False,
    )


def _is_openai_base_url(base_url: str) -> bool:
    parsed = urlsplit(base_url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "api.openai.com"
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and parsed.path.rstrip("/") == "/v1"
    )


def create_openai_client(*, api_key: str, base_url: str, timeout: float) -> AsyncOpenAI:
    """Create a no-retry OpenAI-only client before any credential can be sent."""
    if not api_key.strip():
        raise ValueError("OpenAI API key is not configured")
    if not _is_openai_base_url(base_url):
        raise ValueError("OpenAI base URL is not configured")
    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        max_retries=0,
        http_client=create_http_client(timeout=timeout),
    )


def response_text(response: Response) -> str:
    """Return only terminal message text, rejecting all partial or unsafe alternatives."""
    if response.status != "completed":
        raise ResponseOutputError("response was not completed")
    text_parts: list[str] = []
    for item in response.output:
        if item.type != "message":
            raise ResponseOutputError("unexpected response output")
        for content in item.content:
            if content.type == "refusal":
                raise ResponseOutputError("response was refused")
            if content.type != "output_text" or not content.text:
                raise ResponseOutputError("unexpected message content")
            text_parts.append(content.text)
    text = "".join(text_parts)
    if not text:
        raise ResponseOutputError("response was empty")
    return text
