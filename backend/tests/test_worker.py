from contextlib import nullcontext
from email.parser import BytesParser
from email.policy import default
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app import worker


@pytest.mark.asyncio
@pytest.mark.parametrize("extension", ["png", "jpg"])
@pytest.mark.parametrize("verified_bytes", [False, True])
async def test_image_conversion_preserves_proportions_and_selects_page_orientation(
    tmp_path, extension, verified_bytes
):
    path = tmp_path / f"receipt.{extension}"
    original = b"verified image bytes"
    path.write_bytes(original)

    def respond(request):
        message = BytesParser(policy=default).parsebytes(
            f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode() + request.content
        )
        parts = {
            part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
            for part in message.iter_parts()
        }
        assert parts["fileInput"] == original
        assert parts.get("fitOption") == b"maintainAspectRatio"
        assert parts.get("autoRotate") == b"true"
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, content=b"converted PDF")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await worker._convert_image_to_pdf(
            client, str(path), original if verified_bytes else None
        )
    assert result == b"converted PDF"
    assert path.read_bytes() == original


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

    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, content=b"processed")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await getattr(worker, helper_name)(client, str(path))

    assert result == b"processed"
    assert read_bytes.await_count == 1
    read_method = read_bytes.await_args.args[0]
    assert read_method.__self__ == path
    assert read_method.__name__ == "read_bytes"
    request = requests[0]
    assert str(request.url) == expected_url
    assert b"pdf bytes" in request.content
    if expected_data is not None:
        assert b"pol,eng" in request.content


@pytest.mark.asyncio
async def test_ocr_accepts_converted_pdf_without_reading_original(monkeypatch):
    read = AsyncMock()
    monkeypatch.setattr(worker.asyncio, "to_thread", read)

    def respond(request):
        assert b"converted" in request.content
        return httpx.Response(200, content=b"OCR PDF")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert await worker._ocr_pdf(client, "receipt.png", b"converted") == b"OCR PDF"
    read.assert_not_awaited()


@pytest.mark.asyncio
async def test_text_extraction_does_not_treat_http_error_as_success():
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500))
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await worker._pdf_to_text(client, b"pdf")


def test_stale_recovery_timeout_must_exceed_worker_timeout():
    from app.config import Settings

    with pytest.raises(ValueError, match="recovery timeout"):
        Settings(
            _env_file=None, DOCUMENT_JOB_TIMEOUT_SECONDS=600, DOCUMENT_STALE_PROCESSING_SECONDS=600
        )


@pytest.mark.asyncio
async def test_text_extraction_uses_stirling_text_endpoint_and_output_format():
    import httpx

    def respond(request):
        assert request.url.path.endswith("/api/v1/convert/pdf/text")
        assert b"txt" in request.content and b"outputFormat" in request.content
        return httpx.Response(200, text="receipt")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert await worker._pdf_to_text(client, b"pdf") == "receipt"


@pytest.mark.asyncio
async def test_worker_rejects_document_hash_mismatch_before_calling_stirling(monkeypatch, tmp_path):
    import hashlib
    import uuid
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.documents import service
    from app.documents.schemas import DocumentStatus

    document_id = uuid.uuid4()
    path = tmp_path / "stored.pdf"
    path.write_bytes(b"tampered")
    document = SimpleNamespace(
        id=document_id,
        attempt_count=0,
        next_attempt_at=None,
        last_error_code=None,
        status=DocumentStatus.PENDING,
        storage_path=path.name,
        sha256_hash=hashlib.sha256(b"original").hexdigest(),
        mime_type="application/pdf",
        user_id=uuid.uuid4(),
        original_name="receipt.pdf",
    )

    class Result:
        def scalar_one_or_none(self):
            return document

    class Database:
        def begin_nested(self):
            return nullcontext()

        async def refresh(self, _document):
            pass

        async def execute(self, _statement):
            return Result()

        async def flush(self):
            pass

        async def commit(self):
            pass

        async def rollback(self):
            pass

    class SessionContext:
        async def __aenter__(self):
            return Database()

        async def __aexit__(self, *_args):
            pass

    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(worker, "async_session_factory", SessionContext)
    ocr = AsyncMock()
    convert = AsyncMock()
    monkeypatch.setattr(worker, "_ocr_pdf", ocr)
    monkeypatch.setattr(worker, "_convert_image_to_pdf", convert)

    await worker.process_document({}, str(document_id))

    assert document.status == DocumentStatus.ERROR
    ocr.assert_not_awaited()
    convert.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_passes_verified_pdf_bytes_to_ocr(monkeypatch, tmp_path):
    import hashlib
    import uuid
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.documents import service
    from app.documents.schemas import DocumentStatus

    document_id = uuid.uuid4()
    content = b"%PDF-1.7\nverified original"
    path = tmp_path / "stored.pdf"
    path.write_bytes(content)
    document = SimpleNamespace(
        id=document_id,
        attempt_count=0,
        next_attempt_at=None,
        last_error_code=None,
        status=DocumentStatus.PENDING,
        storage_path=path.name,
        sha256_hash=hashlib.sha256(content).hexdigest(),
        mime_type="application/pdf",
        user_id=uuid.uuid4(),
        original_name="receipt.pdf",
    )

    class Result:
        def scalar_one_or_none(self):
            return document

    class Database:
        def begin_nested(self):
            return nullcontext()

        async def refresh(self, _document):
            pass

        async def execute(self, _statement):
            return Result()

        async def flush(self):
            pass

        async def commit(self):
            pass

        async def rollback(self):
            pass

    class SessionContext:
        async def __aenter__(self):
            return Database()

        async def __aexit__(self, *_args):
            pass

    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(service, "save_extracted_text", AsyncMock())
    monkeypatch.setattr(worker, "async_session_factory", SessionContext)
    ocr = AsyncMock(return_value=b"searchable PDF")
    monkeypatch.setattr(worker, "_ocr_pdf", ocr)
    monkeypatch.setattr(worker, "_pdf_to_text", AsyncMock(return_value=""))

    await worker.process_document({}, str(document_id))

    assert document.status == DocumentStatus.DONE
    assert ocr.await_args.args[2] == content
