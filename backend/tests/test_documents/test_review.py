from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.documents import review_service, service
from app.documents.models import DocumentExtractionRevision
from app.finance.bills_schemas import MutationContext
from app.identity.models import User
from test_documents.fixtures import valid_pdf_bytes


@pytest.mark.integration
async def test_existing_done_upload_uses_saved_text(db_session, tmp_path, monkeypatch):
    """Would fail if preparation reruns OCR instead of using saved OCR text."""
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    user = User(email="review-saved@example.com", password_hash="hash", display_name="Review")
    db_session.add(user)
    await db_session.flush()
    user_id = user.id
    document, _ = await service.store_document(
        db_session, user_id, valid_pdf_bytes(), "receipt.pdf", "application/pdf"
    )
    document.status = "done"
    await service.save_extracted_text(db_session, document.id, "FAKTURA 12,30 PLN", "stirling")
    await db_session.commit()
    extract = AsyncMock(
        return_value={
            "document_type": "invoice",
            "fields": {
                "supplier_name": "Sklep",
                "supplier_tax_id": None,
                "number": None,
                "issue_date": "2026-10-20",
                "sale_date": None,
                "due_date": None,
                "description": "Zakup",
                "payee_iban": None,
                "total": "12.30",
                "currency": "PLN",
            },
            "provenance": {"supplier_name": "llm", "total": "llm", "currency": "llm"},
            "parser_version": "review-v1",
        }
    )
    monkeypatch.setattr(review_service, "extract_review_data", extract)

    result = await review_service.prepare_review(
        db_session,
        user_id,
        document.id,
        refresh=False,
        context=MutationContext(idempotency_key="saved-text"),
    )
    await review_service.process_review_revision(db_session, result.id)
    await db_session.commit()

    assert result.revision == 1
    assert result.status == "ready"
    assert result.data["total_minor"] == 1230
    assert extract.await_args.args == ("FAKTURA 12,30 PLN",)
    assert (await db_session.execute(select(DocumentExtractionRevision))).scalars().all() == [
        result
    ]


@pytest.mark.integration
async def test_reextract_preserves_approved_fields(db_session, tmp_path, monkeypatch):
    """Would fail if a refresh mutates a prior immutable revision."""
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    user = User(email="review-refresh@example.com", password_hash="hash", display_name="Review")
    db_session.add(user)
    await db_session.flush()
    user_id = user.id
    document, _ = await service.store_document(
        db_session, user_id, valid_pdf_bytes(), "receipt.pdf", "application/pdf"
    )
    await service.save_extracted_text(db_session, document.id, "text", "stirling")
    await db_session.flush()
    db_session.add(
        DocumentExtractionRevision(
            user_id=user_id,
            document_id=document.id,
            revision=1,
            status="ready",
            data={"document_type": "invoice", "total_minor": 100, "currency": "PLN"},
            field_provenance={"total_minor": "manual"},
            parser_version="review-v1",
        )
    )
    await db_session.commit()
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
                    "description": None,
                    "payee_iban": None,
                    "total": "2.00",
                    "currency": "PLN",
                },
                "provenance": {"total": "llm", "currency": "llm"},
                "parser_version": "review-v1",
            }
        ),
    )

    latest = await review_service.prepare_review(
        db_session,
        user_id,
        document.id,
        refresh=True,
        context=MutationContext(idempotency_key="refresh"),
    )
    await review_service.process_review_revision(db_session, latest.id)
    await db_session.commit()

    original = await db_session.get(
        DocumentExtractionRevision, latest.id
    )  # identity-map refresh guard
    assert latest.revision == 2
    assert latest.data["total_minor"] == 200
    assert original.id == latest.id
    previous = (
        await db_session.execute(
            select(DocumentExtractionRevision).where(
                DocumentExtractionRevision.document_id == document.id,
                DocumentExtractionRevision.revision == 1,
            )
        )
    ).scalar_one()
    assert previous.data == {"document_type": "invoice", "total_minor": 100, "currency": "PLN"}
    assert previous.field_provenance == {"total_minor": "manual"}


@pytest.mark.integration
async def test_missing_text_requires_explicit_ocr_retry(db_session, tmp_path, monkeypatch):
    """Would fail if review preparation silently starts OCR for an old upload."""
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    user = User(email="review-missing@example.com", password_hash="hash", display_name="Review")
    db_session.add(user)
    await db_session.flush()
    user_id = user.id
    document, _ = await service.store_document(
        db_session, user_id, valid_pdf_bytes(), "old.pdf", "application/pdf"
    )
    document.status = "done"
    await db_session.commit()

    revision = await review_service.prepare_review(
        db_session,
        user_id,
        document.id,
        refresh=False,
        context=MutationContext(idempotency_key="no-text"),
    )

    assert revision.status == "incomplete"
    assert revision.error_code == "ocr_text_unavailable"


def test_statement_or_multibill_never_single_expense():
    """Would fail if unsupported source kinds were narrowed to invoice/receipt."""
    from app.documents.review_schemas import ReviewSuggestion

    suggestion = ReviewSuggestion.model_validate(
        {
            "document_type": "statement",
            "fields": {},
            "provenance": {},
            "parser_version": "review-v1",
        }
    )

    assert suggestion.document_type == "statement"
    assert suggestion.fields.total is None
