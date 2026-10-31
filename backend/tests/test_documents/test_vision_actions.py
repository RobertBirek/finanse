import pytest
from sqlalchemy import select

from app.documents import review_service, service
from app.documents.job_models import DocumentProcessingJob
from app.finance.bills_schemas import MutationContext
from app.identity.models import User
from test_documents.fixtures import valid_jpeg_bytes


@pytest.mark.integration
async def test_vision_local_ocr_does_not_chain_llm_or_replace_review(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    user = User(email="local-ocr@example.com", password_hash="hash", display_name="Local")
    db_session.add(user)
    await db_session.flush()
    document, _ = await service.store_document(
        db_session, user.id, valid_jpeg_bytes(), "receipt.jpg", "image/jpeg"
    )
    document.processing_method = "vision"
    result = await review_service.request_ocr_retry(
        db_session,
        user.id,
        document.id,
        context=MutationContext(idempotency_key="local"),
    )
    assert result.is_new
    job = (await db_session.execute(select(DocumentProcessingJob))).scalars().one()
    assert (job.kind, job.revision_id) == ("local_ocr", None)


@pytest.mark.integration
async def test_second_active_explicit_action_is_rejected(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    user = User(email="local-active@example.com", password_hash="hash", display_name="Local")
    db_session.add(user)
    await db_session.flush()
    document, _ = await service.store_document(
        db_session, user.id, valid_jpeg_bytes(), "receipt.jpg", "image/jpeg"
    )
    document.processing_method = "vision"
    await review_service.request_ocr_retry(
        db_session, user.id, document.id, context=MutationContext(idempotency_key="first")
    )
    with pytest.raises(ValueError, match="processing_active"):
        await review_service.request_ocr_retry(
            db_session, user.id, document.id, context=MutationContext(idempotency_key="second")
        )
