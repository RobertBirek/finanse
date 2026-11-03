from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.documents import job_service, review_service, service
from app.documents.job_models import DocumentVisionPolicy
from app.documents.lifecycle import set_document_archived
from app.documents.models import Document, DocumentText
from app.finance.bills_schemas import MutationContext
from test_documents.fixtures import valid_jpeg_bytes
from test_documents.test_lifecycle import authenticate, make_document, make_job, make_revision

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("work", ["job_pending", "job_processing", "legacy", "text", "old_text"])
async def test_running_work_blocks_archive_with_correct_reason(db_session, async_client, work):
    doc = await make_document(db_session)
    if work.startswith("job_"):
        await make_job(db_session, doc, state=work.removeprefix("job_"))
    elif work == "legacy":
        doc.processing_method = "legacy_ocr"
        doc.status = "processing"
    else:
        await make_revision(db_session, doc, status="pending", method="text")
        if work == "old_text":
            await make_revision(db_session, doc, status="ready", method="text", number=2)
    await db_session.flush()
    authenticate(doc.user_id)
    result = await async_client.post(f"/api/documents/{doc.id}/archive")
    assert result.status_code == 409 and result.json()["code"] == "document_processing_active"
    assert doc.archived_at is None


@pytest.mark.parametrize("state", ["failed", "paused", "superseded", "succeeded"])
async def test_terminal_job_does_not_make_stale_pending_review_block_forever(db_session, state):
    doc = await make_document(db_session)
    revision = await make_revision(db_session, doc, status="pending")
    await make_job(db_session, doc, state=state, revision=revision)
    await set_document_archived(db_session, doc.user_id, doc.id, archived=True)
    assert doc.archived_at is not None


@pytest.mark.parametrize("action", ["vision", "ocr", "text", "retry", "vision_review"])
async def test_archived_document_rejects_fresh_processing_intents(db_session, action):
    doc = await make_document(db_session)
    if action in {"text", "retry"}:
        doc.processing_method = "legacy_ocr"
    db_session.add(DocumentVisionPolicy(id=1, enabled=True, epoch=1))
    await db_session.flush()
    await set_document_archived(db_session, doc.user_id, doc.id, archived=True)
    context = MutationContext(idempotency_key="new-archived-intent")
    with pytest.raises(ValueError, match="document_archived"):
        if action == "vision":
            await job_service.create_vision_intent(db_session, doc.user_id, doc.id, key="new")
        elif action == "ocr":
            await job_service.create_local_ocr_intent(db_session, doc.user_id, doc.id, key="new")
        elif action == "text":
            await review_service.prepare_review(
                db_session, doc.user_id, doc.id, refresh=True, context=context
            )
        elif action == "retry":
            await review_service.request_ocr_retry(db_session, doc.user_id, doc.id, context=context)
        else:
            await review_service.prepare_vision_review(
                db_session, doc.user_id, doc.id, context=context
            )


async def test_worker_claim_and_text_dispatch_skip_archived_rows(db_session, monkeypatch):
    doc = await make_document(db_session)
    await set_document_archived(db_session, doc.user_id, doc.id, archived=True)
    revision = await make_revision(db_session, doc, status="pending", method="text")
    job = await make_job(db_session, doc, state="pending")
    db_session.add(DocumentText(document_id=doc.id, extracted_text="synthetic"))
    await db_session.flush()
    provider = AsyncMock()
    monkeypatch.setattr(review_service, "extract_review_data", provider)
    assert await job_service.claim_processing_job(db_session, job.id, now=datetime.now(UTC)) is None
    assert revision.id not in await review_service.pending_review_ids(db_session)
    await review_service.process_review_revision(db_session, revision.id)
    assert revision.status == "pending"
    provider.assert_not_awaited()


async def test_exact_terminal_intent_replay_after_archive_does_not_create_work(db_session):
    doc = await make_document(db_session)
    job = await job_service.create_local_ocr_intent(db_session, doc.user_id, doc.id, key="original")
    job.state = "succeeded"
    await db_session.flush()
    await set_document_archived(db_session, doc.user_id, doc.id, archived=True)
    replay = await job_service.create_local_ocr_intent(
        db_session, doc.user_id, doc.id, key="original"
    )
    assert replay.id == job.id and replay.state == "succeeded"


async def test_archived_duplicate_upload_never_resurrects_or_refunds_storage(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(service.settings, "DOCUMENT_VISION_ENABLED", False)
    (tmp_path / ".backup.lock").touch()
    owner = (await make_document(db_session)).user_id
    content = valid_jpeg_bytes()
    doc, duplicate = await service.store_document(
        db_session, owner, content, "synthetic.jpg", "image/jpeg"
    )
    assert not duplicate
    doc.status = "done"
    await db_session.flush()
    await set_document_archived(db_session, owner, doc.id, archived=True)
    timestamp = doc.archived_at
    total = await db_session.scalar(
        select(func.sum(Document.size_bytes)).where(Document.user_id == owner)
    )
    replay, duplicate = await service.store_document(
        db_session, owner, content, "synthetic-again.jpg", "image/jpeg"
    )
    assert duplicate and replay.id == doc.id and replay.archived_at == timestamp
    assert (
        await db_session.scalar(
            select(func.sum(Document.size_bytes)).where(Document.user_id == owner)
        )
        == total
    )


@pytest.mark.parametrize("path", ["review/prepare", "vision/prepare", "retry-ocr"])
async def test_archived_processing_api_returns_specific_domain_code(db_session, async_client, path):
    from app.documents.review_router import processing_action_rate_limit
    from app.main import app

    doc = await make_document(db_session)
    db_session.add(DocumentVisionPolicy(id=1, enabled=True, epoch=1))
    await db_session.flush()
    await set_document_archived(db_session, doc.user_id, doc.id, archived=True)
    authenticate(doc.user_id)
    app.dependency_overrides[processing_action_rate_limit] = lambda: None
    result = await async_client.post(
        f"/api/documents/{doc.id}/{path}", headers={"Idempotency-Key": "fresh"}
    )
    assert result.status_code == 409 and result.json()["code"] == "document_archived"
