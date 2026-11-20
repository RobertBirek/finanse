import uuid
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image
from pypdf import PdfReader

from app.config import settings
from app.documents.scan import ScanTooLargeError, assemble_scan
from app.documents.schemas import DocumentResponse
from app.documents.validation import validate_document_content


def _photo(format_: str, size: tuple[int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, "white").save(output, format=format_)
    return output.getvalue()


@pytest.mark.asyncio
async def test_camera_images_make_one_pdf_in_the_selected_order():
    png = _photo("PNG", (80, 120))
    jpeg = _photo("JPEG", (105, 70))
    pages = [(jpeg, "image/jpeg"), (png, "image/png")]
    pdf = await assemble_scan(pages)
    assert await validate_document_content(pdf, "application/pdf") == "application/pdf"
    assert pdf == await assemble_scan(pages)
    assert [
        (page.mediabox.width, page.mediabox.height) for page in PdfReader(BytesIO(pdf)).pages
    ] == [(105, 70), (80, 120)]


@pytest.mark.asyncio
async def test_scan_rejects_total_bytes_and_page_count_before_decoding(monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_MAX_FILE_BYTES", 10)
    with pytest.raises(ScanTooLargeError):
        await assemble_scan([(b"123456", "image/jpeg"), (b"123456", "image/jpeg")])
    monkeypatch.setattr(settings, "DOCUMENT_SCAN_MAX_PAGES", 2)
    with pytest.raises(ScanTooLargeError):
        await assemble_scan([(b"x", "image/jpeg")] * 3)


@pytest.mark.asyncio
async def test_camera_multipart_stores_one_new_pdf(monkeypatch):
    from app.database import get_db
    from app.documents import router
    from app.identity.router import get_current_user

    owner = SimpleNamespace(id=uuid.uuid4())
    now = datetime.now(UTC)
    document = DocumentResponse(
        id=uuid.uuid4(),
        user_id=owner.id,
        filename="scan.pdf",
        original_name="scan.pdf",
        mime_type="application/pdf",
        sha256_hash="synthetic",
        size_bytes=1,
        status="done",
        created_at=now,
        updated_at=now,
    )
    store = AsyncMock(return_value=(document, False))
    monkeypatch.setattr(router.service, "store_document", store)
    monkeypatch.setattr(router.service, "document_responses", AsyncMock(return_value=[document]))
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    app = FastAPI()
    app.include_router(router.router, prefix="/api/documents")
    app.dependency_overrides.update(
        {
            get_db: lambda: db,
            get_current_user: lambda: owner,
            router.upload_rate_limit: lambda: None,
        }
    )
    pages = [
        ("pages", ("first.jpg", _photo("JPEG", (105, 70)), "image/jpeg")),
        ("pages", ("second.png", _photo("PNG", (80, 120)), "image/png")),
    ]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test.invalid"
    ) as client:
        response = await client.post("/api/documents/upload", files=pages)
        mixed = await client.post(
            "/api/documents/upload",
            files=[*pages, ("file", ("other.png", _photo("PNG", (80, 120)), "image/png"))],
        )

    assert response.status_code == 200
    assert response.json()["document"]["id"] == str(document.id)
    assert mixed.status_code == 422
    store.assert_awaited_once()
    session, user_id, content, filename, mime = store.call_args.args
    assert session is db and user_id == owner.id and filename.endswith(".pdf")
    assert mime == "application/pdf"
    assert [page.mediabox.width for page in PdfReader(BytesIO(content)).pages] == [105, 80]
