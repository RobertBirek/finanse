import asyncio
import os
import sys
from io import BytesIO

import pytest
from PIL import Image
from pypdf import PdfWriter

from test_documents.fixtures import valid_jpeg_bytes, valid_pdf_bytes, valid_png_bytes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content,mime",
    [
        (valid_pdf_bytes(), "application/pdf"),
        (valid_png_bytes(), "image/png"),
        (valid_jpeg_bytes(), "image/jpeg"),
    ],
)
async def test_valid_files_pass_isolated_validation(content, mime):
    from app.documents.validation import validate_document_content

    assert await validate_document_content(content, mime) == mime


def test_detect_document_mime_type_rejects_avif_branded_container():
    from app.documents.validation_process import detect_document_mime_type

    # A valid HEIC payload with an AVIF-compatible brand must not bypass the format allowlist.
    from test_documents.fixtures import valid_heic_bytes

    content = valid_heic_bytes().replace(b"heic", b"avif", 1)
    assert detect_document_mime_type(content) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["mismatch", "truncated", "encrypted", "empty", "pages", "pixels", "frames"]
)
async def test_invalid_or_excessive_documents_rejected(kind, monkeypatch):
    from app.config import settings
    from app.documents.validation import UnsupportedDocumentFormatError, validate_document_content

    content, mime = valid_pdf_bytes(), "application/pdf"
    if kind == "mismatch":
        content = valid_png_bytes()
    elif kind == "truncated":
        content = content[:-3]
    elif kind in {"encrypted", "empty", "pages"}:
        writer = PdfWriter()
        for _ in range(3 if kind == "pages" else int(kind == "encrypted")):
            writer.add_blank_page(width=72, height=72)
        if kind == "encrypted":
            writer.encrypt("secret")
        if kind == "pages":
            monkeypatch.setattr(settings, "DOCUMENT_MAX_PAGES", 2)
        output = BytesIO()
        writer.write(output)
        content = output.getvalue()
    else:
        output = BytesIO()
        image = Image.new("RGB", (3, 3))
        if kind == "pixels":
            monkeypatch.setattr(settings, "DOCUMENT_MAX_IMAGE_PIXELS", 8)
            image.save(output, format="PNG")
        else:
            image.save(
                output, format="PNG", save_all=True, append_images=[Image.new("RGB", (3, 3), "red")]
            )
        content, mime = output.getvalue(), "image/png"
    with pytest.raises(UnsupportedDocumentFormatError):
        await validate_document_content(content, mime)


@pytest.mark.asyncio
async def test_process_timeout_kills_and_reaps_child(tmp_path):
    from app.documents.validation import UnsupportedDocumentFormatError, run_validation_process

    pidfile = tmp_path / "pid"
    code = f"import os,time;open({str(pidfile)!r},'w').write(str(os.getpid()));time.sleep(60)"
    with pytest.raises(UnsupportedDocumentFormatError):
        await run_validation_process([sys.executable, "-c", code], b"", 0.5)
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


@pytest.mark.asyncio
async def test_cancelled_process_is_reaped(tmp_path):
    from app.documents.validation import run_validation_process

    pidfile = tmp_path / "pid"
    code = f"import os,time;open({str(pidfile)!r},'w').write(str(os.getpid()));time.sleep(60)"
    task = asyncio.create_task(run_validation_process([sys.executable, "-c", code], b"", 30))
    async with asyncio.timeout(3):
        while not pidfile.exists():
            await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["print('x'*5000)", "print('invalid')", "raise SystemExit(2)"])
async def test_invalid_process_output_fails_closed(code):
    from app.documents.validation import UnsupportedDocumentFormatError, run_validation_process

    with pytest.raises(UnsupportedDocumentFormatError):
        await run_validation_process([sys.executable, "-c", code], b"", 3)


@pytest.mark.asyncio
async def test_busy_slot_returns_unavailable_and_is_reusable(monkeypatch):
    from app.config import settings
    from app.documents import validation

    monkeypatch.setattr(settings, "DOCUMENT_VALIDATION_CONCURRENCY", 1)
    monkeypatch.setattr(settings, "DOCUMENT_VALIDATION_QUEUE_SECONDS", 0.02)
    semaphore = validation.validation_slots()
    await semaphore.acquire()
    try:
        with pytest.raises(validation.DocumentValidationUnavailableError):
            await validation.validate_document_content(valid_png_bytes(), "image/png")
    finally:
        semaphore.release()
    assert await validation.validate_document_content(valid_png_bytes(), "image/png") == "image/png"
