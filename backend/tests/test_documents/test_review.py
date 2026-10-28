from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.documents import review_service, service
from app.documents.models import DocumentExtractionRevision
from app.documents.review_schemas import ReviewSuggestion
from app.finance.bills_schemas import MutationContext
from app.finance.models import FinanceCommandReceipt
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
        return_value=ReviewSuggestion.model_validate(
            {
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
                        "description": None,
                        "payee_iban": None,
                        "total": "2.00",
                        "currency": "PLN",
                    },
                    "provenance": {"total": "llm", "currency": "llm"},
                    "parser_version": "review-v1",
                }
            )
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


@pytest.mark.integration
async def test_llm_timeout_is_visible_while_saved_review_remains_available(
    db_session, tmp_path, monkeypatch
):
    """Would fail if an LLM timeout were hidden as a successful no-document result."""
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    user = User(email="review-timeout@example.com", password_hash="hash", display_name="Review")
    db_session.add(user)
    await db_session.flush()
    document, _ = await service.store_document(
        db_session, user.id, valid_pdf_bytes(), "timeout.pdf", "application/pdf"
    )
    await service.save_extracted_text(db_session, document.id, "review manually", "stirling")
    pending = await review_service.prepare_review(
        db_session,
        user.id,
        document.id,
        refresh=False,
        context=MutationContext(idempotency_key="timeout"),
    )
    monkeypatch.setattr(
        review_service,
        "extract_review_data",
        AsyncMock(side_effect=review_service.ReviewExtractionError("llm_unavailable")),
    )

    await review_service.process_review_revision(db_session, pending.id)
    visible = await review_service.get_review(db_session, user.id, document.id)
    manual = await review_service.prepare_review(
        db_session,
        user.id,
        document.id,
        refresh=False,
        context=MutationContext(idempotency_key="manual-after-timeout"),
    )

    assert visible is not None
    assert (visible.status, visible.error_code) == ("incomplete", "llm_unavailable")
    assert manual.id == pending.id


@pytest.mark.integration
async def test_foreign_document_is_not_available_to_review_service(
    db_session, tmp_path, monkeypatch
):
    """Would fail if review preparation leaked another owner's document as a non-404 result."""
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    owner = User(email="review-owner@example.com", password_hash="hash", display_name="Owner")
    other = User(email="review-other@example.com", password_hash="hash", display_name="Other")
    db_session.add_all([owner, other])
    await db_session.flush()
    document, _ = await service.store_document(
        db_session, owner.id, valid_pdf_bytes(), "private.pdf", "application/pdf"
    )

    assert await review_service.get_review(db_session, other.id, document.id) is None
    with pytest.raises(LookupError, match="document_not_found"):
        await review_service.prepare_review(
            db_session,
            other.id,
            document.id,
            refresh=False,
            context=MutationContext(idempotency_key="foreign"),
        )


@pytest.mark.integration
async def test_foreign_document_review_route_returns_404(
    async_client, db_session, tmp_path, monkeypatch
):
    """Would fail if the public review route exposed a foreign document's review state."""
    from types import SimpleNamespace

    from app.identity.router import get_current_user
    from app.main import app

    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    owner = User(email="review-route-owner@example.com", password_hash="hash", display_name="Owner")
    other = User(email="review-route-other@example.com", password_hash="hash", display_name="Other")
    db_session.add_all([owner, other])
    await db_session.flush()
    document, _ = await service.store_document(
        db_session, owner.id, valid_pdf_bytes(), "private-route.pdf", "application/pdf"
    )
    await db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=other.id)
    try:
        response = await async_client.get(f"/api/documents/{document.id}/review")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Review not found"}


@pytest.mark.integration
async def test_retry_ocr_replays_same_key_without_resetting_again(
    db_session, tmp_path, monkeypatch
):
    """Would fail if repeated retry requests reset an exhausted OCR budget more than once."""
    from app.audit.models import AuditEvent

    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    user = User(email="review-retry@example.com", password_hash="hash", display_name="Review")
    db_session.add(user)
    await db_session.flush()
    document, _ = await service.store_document(
        db_session, user.id, valid_pdf_bytes(), "failed.pdf", "application/pdf"
    )
    document.status, document.attempt_count, document.last_error_code = "error", 3, "output_limit"
    first, _first_response = await review_service.request_ocr_retry(
        db_session, user.id, document.id, context=MutationContext(idempotency_key="retry-once")
    )
    await db_session.commit()
    first.attempt_count = 2  # simulate the queued OCR worker consuming the retried budget
    await db_session.commit()

    replayed, replay_response = await review_service.request_ocr_retry(
        db_session, user.id, document.id, context=MutationContext(idempotency_key="retry-once")
    )

    receipts = (await db_session.execute(select(FinanceCommandReceipt))).scalars().all()
    audits = (
        (await db_session.execute(select(AuditEvent).where(AuditEvent.action == "retry_ocr")))
        .scalars()
        .all()
    )
    assert replayed.id == first.id
    assert replayed.attempt_count == 2
    assert replay_response == {"id": str(document.id), "status": "pending"}
    assert len(receipts) == 1
    assert len(audits) == 1


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
