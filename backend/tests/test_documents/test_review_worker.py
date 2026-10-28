from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import worker
from app.documents import review_service, service
from app.documents.models import DocumentExtractionRevision
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
            return_value={
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
        ),
    )

    await worker.process_document({}, str(document_id))

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
