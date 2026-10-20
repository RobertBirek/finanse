from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import worker


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("helper_name", "expected_url", "expected_data"),
    [
        ("_convert_image_to_pdf", worker.STIRLING_IMG_TO_PDF_URL, None),
        ("_ocr_pdf", worker.STIRLING_OCR_URL, {"languages": "pol,eng", "ocrType": "skip-text"}),
    ],
)
async def test_worker_file_uploads_read_files_off_event_loop(
    monkeypatch, tmp_path, helper_name, expected_url, expected_data
):
    path = tmp_path / "receipt.pdf"
    path.write_bytes(b"pdf bytes")
    read_bytes = AsyncMock(return_value=b"pdf bytes")
    monkeypatch.setattr(worker, "asyncio", SimpleNamespace(to_thread=read_bytes), raising=False)

    response = SimpleNamespace(content=b"processed", raise_for_status=lambda: None)
    client = SimpleNamespace(post=AsyncMock(return_value=response))

    result = await getattr(worker, helper_name)(client, str(path))

    assert result == b"processed"
    assert read_bytes.await_count == 1
    read_method = read_bytes.await_args.args[0]
    assert read_method.__self__ == path
    assert read_method.__name__ == "read_bytes"
    request = client.post.await_args
    assert request.args[0] == expected_url
    assert request.kwargs["files"] == {"fileInput": (path.name, b"pdf bytes")}
    if expected_data is not None:
        assert request.kwargs["data"] == expected_data


@pytest.mark.asyncio
async def test_ocr_accepts_converted_pdf_without_reading_original(monkeypatch):
    read = AsyncMock()
    monkeypatch.setattr(worker.asyncio, "to_thread", read)
    response = SimpleNamespace(content=b"OCR PDF", raise_for_status=lambda: None)
    client = SimpleNamespace(post=AsyncMock(return_value=response))
    assert await worker._ocr_pdf(client, "receipt.png", b"converted") == b"OCR PDF"
    read.assert_not_awaited()
    assert client.post.await_args.kwargs["files"]["fileInput"][1] == b"converted"


@pytest.mark.asyncio
async def test_text_extraction_does_not_treat_http_error_as_success():
    import httpx

    response = httpx.Response(500, request=httpx.Request("POST", worker.STIRLING_PDF_TO_TEXT_URL))
    client = SimpleNamespace(post=AsyncMock(return_value=response))
    with pytest.raises(httpx.HTTPStatusError):
        await worker._pdf_to_text(client, b"pdf")


def test_stale_recovery_timeout_must_exceed_worker_timeout():
    from app.config import Settings

    with pytest.raises(ValueError, match="recovery timeout"):
        Settings(
            _env_file=None, DOCUMENT_JOB_TIMEOUT_SECONDS=600, DOCUMENT_STALE_PROCESSING_SECONDS=600
        )
