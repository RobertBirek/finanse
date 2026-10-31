from hashlib import sha256
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import worker
from app.documents import review_service, service
from app.documents.models import DocumentExtractionRevision
from app.documents.review_schemas import ReviewSuggestion
from app.identity.models import User
from app.inbox.models import InboxItem
from test_documents.fixtures import valid_pdf_bytes


@pytest.mark.integration
async def test_worker_creates_review_revision_not_legacy_inbox(
    test_database, tmp_path, monkeypatch
):
    """Would fail if new OCR keeps creating the legacy parallel Inbox expense."""
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(worker, "async_session_factory", sessions)
    async with sessions() as db:
        user = User(email="review-worker@example.com", password_hash="hash", display_name="Review")
        db.add(user)
        await db.flush()
        document, _ = await service.store_document(
            db, user.id, valid_pdf_bytes(), "receipt.pdf", "application/pdf"
        )
        legacy = InboxItem(
            user_id=user.id,
            content="Legacy processed suggestion",
            source_type="document",
            is_processed=True,
            agent_suggestion={"document_id": str(document.id)},
        )
        db.add(legacy)
        await db.commit()
        document_id = document.id
        legacy_id = legacy.id
    monkeypatch.setattr(worker, "_ocr_pdf", AsyncMock(return_value=b"pdf"))
    monkeypatch.setattr(worker, "_pdf_to_text", AsyncMock(return_value="receipt text"))
    monkeypatch.setattr(
        review_service,
        "extract_review_data",
        AsyncMock(
            return_value=ReviewSuggestion.model_validate(
                {
                    "document_type": "receipt",
                    "fields": {
                        "supplier_name": None,
                        "supplier_tax_id": None,
                        "number": None,
                        "issue_date": None,
                        "sale_date": None,
                        "due_date": None,
                        "description": "Zakup",
                        "payee_iban": None,
                        "total": "1.00",
                        "currency": "PLN",
                    },
                    "provenance": {"total": "llm", "currency": "llm"},
                    "parser_version": "review-v1",
                }
            )
        ),
    )

    await worker.process_document({}, str(document_id))
    await worker.process_document({}, str(document_id))  # duplicate delivery after recovery

    async with sessions() as db:
        revisions = (
            (
                await db.execute(
                    select(DocumentExtractionRevision).where(
                        DocumentExtractionRevision.document_id == document_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert [(item.revision, item.status, item.data["total_minor"]) for item in revisions] == [
            (1, "ready", 100)
        ]
        inbox = (await db.execute(select(InboxItem))).scalars().all()
        assert [(item.id, item.is_processed, item.content) for item in inbox] == [
            (legacy_id, True, "Legacy processed suggestion")
        ]


@pytest.mark.integration
async def test_jpeg_ocr_receives_exif_normalized_bytes(test_database, tmp_path, monkeypatch):
    """Would fail if legacy JPEG OCR bypassed the metadata-safe derivative."""
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(worker, "async_session_factory", sessions)
    source = Image.new("RGB", (2, 4), "red")
    exif = Image.Exif()
    exif[274] = 6
    exif[34853] = {1: "N", 2: (52.0, 0.0, 0.0)}
    source_bytes = BytesIO()
    source.save(source_bytes, format="JPEG", exif=exif)
    original = source_bytes.getvalue()
    async with sessions() as db:
        user = User(email="jpeg-normalized@example.com", password_hash="hash", display_name="JPEG")
        db.add(user)
        await db.flush()
        document, _ = await service.store_document(
            db, user.id, original, "receipt.jpg", "image/jpeg"
        )
        await db.commit()
        document_id = document.id
        stored_path = tmp_path / document.storage_path

    captured: list[bytes] = []

    async def convert(_client, _path, image_content=None):
        assert image_content is not None
        captured.append(image_content)
        return b"converted"

    monkeypatch.setattr(worker, "_convert_image_to_pdf", convert)
    monkeypatch.setattr(worker, "_ocr_pdf", AsyncMock(return_value=b"pdf"))
    monkeypatch.setattr(worker, "_pdf_to_text", AsyncMock(return_value=""))

    await worker.process_document({}, str(document_id))

    assert sha256(original).digest() == sha256(stored_path.read_bytes()).digest()
    assert len(captured) == 1
    with Image.open(BytesIO(captured[0])) as image:
        assert image.size == (4, 2)
        assert not image.getexif()
