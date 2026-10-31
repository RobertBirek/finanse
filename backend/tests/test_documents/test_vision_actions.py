import pytest
from sqlalchemy import select

from app.documents import review_service, service
from app.documents.job_models import DocumentProcessingJob, DocumentVisionPolicy
from app.finance.bills_schemas import MutationContext
from app.finance.models import FinanceCommandReceipt
from app.identity.models import User
from test_documents.fixtures import valid_jpeg_bytes


@pytest.mark.integration
async def test_vision_local_ocr_does_not_chain_llm_or_replace_review(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(service.settings, "DOCUMENT_VISION_ENABLED", True)
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


@pytest.mark.integration
async def test_processing_actions_rate_limit_before_creating_work(
    async_client, db_session, tmp_path, monkeypatch
):
    """The real Redis-backed dependency rejects both action routes before their receipts/jobs."""
    from test_security.test_rate_limit import TRUSTED_ORIGIN, FakeRedis

    from app.identity.service import create_session
    from app.security import rate_limit

    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(service.settings, "DOCUMENT_VISION_ENABLED", True)
    monkeypatch.setattr(rate_limit.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(rate_limit.settings, "SECRET_KEY", "s" * 32)
    monkeypatch.setattr(rate_limit.settings, "_trusted_origins", (TRUSTED_ORIGIN,))
    monkeypatch.setattr(rate_limit.settings, "DOCUMENT_PROCESSING_ACTION_RATE_LIMIT", 1)
    monkeypatch.setattr(
        rate_limit.settings, "DOCUMENT_PROCESSING_ACTION_RATE_LIMIT_WINDOW_SECONDS", 60
    )
    redis = FakeRedis()
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: redis)
    user = User(email="action-limit@example.com", password_hash="hash", display_name="Action")
    db_session.add_all([user, DocumentVisionPolicy(id=1, enabled=True, epoch=1)])
    await db_session.flush()
    document, _ = await service.store_document(
        db_session, user.id, valid_jpeg_bytes(), "receipt.jpg", "image/jpeg"
    )
    # The upload intent is terminal for this test; the limiter must run before either action.
    job = (await db_session.execute(select(DocumentProcessingJob))).scalars().one()
    job.state = "failed"
    session_token, csrf_token, _ = await create_session(db_session, user.id)
    await db_session.commit()
    key = "security:rate-limit:v1:document-processing-action:" + rate_limit.hash_identifier(
        str(user.id)
    )
    redis.counts[key] = 1
    headers = {
        "Origin": TRUSTED_ORIGIN,
        "X-CSRF-Token": csrf_token,
        "Cookie": f"advisor_session={session_token}; advisor_csrf={csrf_token}",
    }
    vision = await async_client.post(
        f"/api/documents/{document.id}/vision/prepare",
        headers={**headers, "Idempotency-Key": "limited-vision"},
    )
    retry = await async_client.post(
        f"/api/documents/{document.id}/retry-ocr",
        headers={**headers, "Idempotency-Key": "limited-ocr"},
    )

    receipts = (await db_session.execute(select(FinanceCommandReceipt))).scalars().all()
    jobs = (await db_session.execute(select(DocumentProcessingJob))).scalars().all()
    assert [response.status_code for response in (vision, retry)] == [429, 429]
    assert receipts == []
    assert [(item.id, item.state) for item in jobs] == [(job.id, "failed")]
    assert len(redis.calls) == 2
