from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.documents import service
from app.documents.job_models import DocumentProcessingJob, DocumentVisionPolicy
from app.documents.models import DocumentExtractionRevision, DocumentText
from app.identity.models import User
from test_documents.fixtures import valid_jpeg_bytes, valid_pdf_bytes


@pytest.mark.integration
async def test_new_vision_upload_enqueues_existing_durable_job_after_commit(
    async_client, db_session, tmp_path, monkeypatch
):
    """The upload never sends vision rows to the legacy OCR entry point."""
    from types import SimpleNamespace

    from app import worker
    from app.identity.router import get_current_user
    from app.main import app

    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(service.settings, "DOCUMENT_VISION_ENABLED", True)
    user = User(email="vision-route@example.com", password_hash="hash", display_name="Vision")
    db_session.add_all([user, DocumentVisionPolicy(id=1, enabled=True, epoch=7)])
    await db_session.commit()
    durable, legacy = AsyncMock(), AsyncMock()
    monkeypatch.setattr(worker, "enqueue_process_document_job", durable)
    monkeypatch.setattr(worker, "enqueue_process_document", legacy)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user.id)
    try:
        response = await async_client.post(
            "/api/documents/upload",
            files={"file": ("receipt.jpg", valid_jpeg_bytes(), "image/jpeg")},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    document_id = response.json()["document"]["id"]
    job = (
        await db_session.execute(
            select(DocumentProcessingJob).where(DocumentProcessingJob.document_id == document_id)
        )
    ).scalar_one()
    durable.assert_awaited_once_with(str(job.id))
    legacy.assert_not_awaited()


@pytest.mark.integration
async def test_vision_upload_redis_failure_keeps_durable_job_for_dispatch(
    async_client, db_session, tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from app import worker
    from app.identity.router import get_current_user
    from app.main import app

    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(service.settings, "DOCUMENT_VISION_ENABLED", True)
    user = User(email="vision-outage@example.com", password_hash="hash", display_name="Vision")
    db_session.add_all([user, DocumentVisionPolicy(id=1, enabled=True, epoch=7)])
    await db_session.commit()
    monkeypatch.setattr(
        worker, "enqueue_process_document_job", AsyncMock(side_effect=OSError("down"))
    )
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user.id)
    try:
        response = await async_client.post(
            "/api/documents/upload",
            files={"file": ("receipt.jpg", valid_jpeg_bytes(), "image/jpeg")},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    job = (await db_session.execute(select(DocumentProcessingJob))).scalar_one()
    assert job.state == "pending"
    calls = []

    class Redis:
        async def enqueue_job(self, *args, **kwargs):
            calls.append((args, kwargs))

    await worker.dispatch_document_jobs({"redis": Redis()})
    assert calls == [(("process_document_job", str(job.id)), {"_job_id": f"document-job:{job.id}"})]


@pytest.mark.integration
async def test_enabled_policy_routes_new_image_to_vision_in_same_transaction(
    db_session, tmp_path, monkeypatch
):
    """A new image gets its immutable routing decision and durable intent before commit."""
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(service.settings, "DOCUMENT_VISION_ENABLED", True)
    user = User(email="vision-upload@example.com", password_hash="hash", display_name="Vision")
    db_session.add_all([user, DocumentVisionPolicy(id=1, enabled=True, epoch=7)])
    await db_session.flush()

    document, duplicate = await service.store_document(
        db_session, user.id, valid_jpeg_bytes(), "receipt.jpg", "image/jpeg"
    )

    assert not duplicate
    assert document.processing_method == "vision"
    assert (
        await db_session.execute(select(DocumentExtractionRevision))
    ).scalars().one().input_method == "image"
    job = (await db_session.execute(select(DocumentProcessingJob))).scalars().one()
    assert (job.kind, job.document_id, job.revision_id, job.state) == (
        "vision",
        document.id,
        job.revision_id,
        "pending",
    )
    assert (await db_session.execute(select(DocumentText))).scalars().all() == []


@pytest.mark.integration
async def test_duplicate_image_after_flag_change_creates_no_new_vision_intent(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(service.settings, "DOCUMENT_VISION_ENABLED", True)
    user = User(email="vision-duplicate@example.com", password_hash="hash", display_name="Vision")
    db_session.add_all([user, DocumentVisionPolicy(id=1, enabled=True, epoch=7)])
    await db_session.flush()
    first, duplicate = await service.store_document(
        db_session, user.id, valid_jpeg_bytes(), "a.jpg", "image/jpeg"
    )
    assert not duplicate
    before_jobs = (await db_session.execute(select(DocumentProcessingJob))).scalars().all()
    before_revisions = (
        (await db_session.execute(select(DocumentExtractionRevision))).scalars().all()
    )
    monkeypatch.setattr(service.settings, "DOCUMENT_VISION_ENABLED", False)
    again, duplicate = await service.store_document(
        db_session, user.id, valid_jpeg_bytes(), "b.jpg", "image/jpeg"
    )
    assert duplicate and again.id == first.id
    assert (await db_session.execute(select(DocumentProcessingJob))).scalars().all() == before_jobs
    assert (
        await db_session.execute(select(DocumentExtractionRevision))
    ).scalars().all() == before_revisions


@pytest.mark.integration
async def test_pdf_stays_legacy(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(service.settings, "DOCUMENT_VISION_ENABLED", True)
    user = User(email="vision-pdf@example.com", password_hash="hash", display_name="Vision")
    db_session.add_all([user, DocumentVisionPolicy(id=1, enabled=True, epoch=1)])
    await db_session.flush()

    document, _ = await service.store_document(
        db_session, user.id, valid_pdf_bytes(), "receipt.pdf", "application/pdf"
    )
    assert document.processing_method == "legacy_ocr"
    assert (await db_session.execute(select(DocumentProcessingJob))).scalars().all() == []
