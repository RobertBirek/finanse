import gzip

import httpx
import pytest


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers,data",
    [
        ({}, b"x" * 100),
        ({"Content-Length": "1"}, b"x" * 100),
        ({"Content-Encoding": "gzip"}, gzip.compress(b"x" * 100)),
    ],
)
async def test_ocr_stream_rejects_expansion_and_closes(headers, data):
    from app.documents.ocr_client import OCRResponseTooLargeError, post_bounded

    stream = Chunks([data[:3], data[3:]])
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, headers=headers, stream=stream))
    ) as client:
        with pytest.raises(OCRResponseTooLargeError):
            await post_bounded(client, "http://ocr", {}, 20)
    assert stream.closed


@pytest.mark.asyncio
async def test_ocr_stream_accepts_exact_limit():
    from app.documents.ocr_client import post_bounded

    stream = Chunks([b"ab", b"cd"])
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))
    ) as client:
        assert await post_bounded(client, "http://ocr", {}, 4) == b"abcd"
    assert stream.closed
