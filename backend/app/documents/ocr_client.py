from typing import Any

import httpx


class OCRResponseTooLargeError(ValueError):
    """Unsafe response size or unsupported encoded response."""


async def read_bounded_response(response: httpx.Response, max_bytes: int) -> bytes:
    response.raise_for_status()
    # Request identity and reject unexpected compression BEFORE httpx decompresses
    # a chunk. Post-decompression checks alone cannot prevent allocation bombs.
    if response.headers.get("content-encoding", "identity").lower() != "identity":
        raise OCRResponseTooLargeError("Encoded OCR responses are not accepted")
    length = response.headers.get("content-length")
    if length and (not length.isdecimal() or int(length) > max_bytes):
        raise OCRResponseTooLargeError("OCR response exceeds limit")
    if response.is_stream_consumed:
        if len(response.content) > max_bytes:
            raise OCRResponseTooLargeError("OCR response exceeds limit")
        return response.content
    data = bytearray()
    async for chunk in response.aiter_raw(chunk_size=64 * 1024):
        if len(data) + len(chunk) > max_bytes:
            raise OCRResponseTooLargeError("OCR response exceeds limit")
        data.extend(chunk)
    return bytes(data)


async def post_bounded(
    client: httpx.AsyncClient,
    url: str,
    files: dict[str, Any],
    max_bytes: int,
    data: dict[str, str] | None = None,
) -> bytes:
    async with client.stream(
        "POST", url, files=files, data=data, headers={"Accept-Encoding": "identity"}
    ) as response:
        return await read_bounded_response(response, max_bytes)
