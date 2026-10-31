import pytest
from sqlalchemy import select

from app.documents import service
from app.documents.job_models import DocumentProcessingJob, DocumentVisionPolicy
from app.documents.models import DocumentExtractionRevision, DocumentText
from app.identity.models import User
from test_documents.fixtures import valid_jpeg_bytes, valid_pdf_bytes


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
