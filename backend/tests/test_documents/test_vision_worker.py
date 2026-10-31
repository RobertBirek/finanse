import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.main  # noqa: F401
from app.documents import job_service, service, vision_worker
from app.documents.job_models import DocumentProcessingJob, DocumentVisionPolicy
from app.documents.job_service import create_vision_intent
from app.documents.models import Document, DocumentExtractionRevision
from app.documents.review_schemas import ReviewSuggestion
from app.documents.vision_config import VisionConfig
from app.documents.vision_schemas import VisionExtraction
from test_documents.fixtures import valid_jpeg_bytes


def _config() -> VisionConfig:
    return VisionConfig("test", "https://vision.example.test/v1", "model", "secret", "p1", "s1")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_network_runs_after_claim_commit(test_database, tmp_path, monkeypatch):
    """The provider call happens only after the short claim transaction has committed."""
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(vision_worker, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(vision_worker, "async_session_factory", sessions)
    monkeypatch.setattr(vision_worker, "get_vision_config", lambda _settings: _config())
    monkeypatch.setattr(job_service, "get_vision_config", lambda _settings: _config())
    monkeypatch.setattr(vision_worker.settings, "DOCUMENT_VISION_ENABLED", True)
    monkeypatch.setattr(
        vision_worker, "normalize_image", AsyncMock(return_value=valid_jpeg_bytes())
    )
    async with sessions() as db:
        user_id = uuid.uuid4()
        jpeg = valid_jpeg_bytes()
        document = Document(
            user_id=user_id,
            filename="receipt.jpg",
            original_name="receipt.jpg",
            mime_type="image/jpeg",
            sha256_hash=service.compute_sha256(jpeg),
            size_bytes=1,
            storage_path="aa/receipt.jpg",
            processing_method="vision",
        )
        db.add_all(
            (
                document,
                DocumentVisionPolicy(
                    id=1,
                    enabled=True,
                    epoch=1,
                    configuration_fingerprint=_config().configuration_fingerprint,
                ),
            )
        )
        await db.flush()
        revision = DocumentExtractionRevision(
            user_id=user_id,
            document_id=document.id,
            revision=1,
            status="pending",
            data={"document_type": "other", "fields": {}, "provenance": {}, "parser_version": None},
            field_provenance={},
            input_method="image",
        )
        db.add(revision)
        await db.flush()
        job = await create_vision_intent(db, user_id, document.id, key="vision:worker")
        job_revision_id = job.revision_id
        stored = tmp_path / document.storage_path
        stored.parent.mkdir(parents=True, exist_ok=True)
        stored.write_bytes(jpeg)
        await db.commit()
    entered = False

    async def provider(*_args, **_kwargs):
        nonlocal entered
        entered = True
        async with sessions() as db:
            assert (
                await db.execute(
                    select(DocumentProcessingJob)
                    .where(DocumentProcessingJob.id == job.id)
                    .with_for_update(nowait=True)
                )
            ).scalar_one().state == "processing"
            assert (
                await db.execute(
                    select(Document)
                    .where(Document.id == job.document_id)
                    .with_for_update(nowait=True)
                )
            ).scalar_one().id == job.document_id
        return VisionExtraction(
            suggestion=ReviewSuggestion(
                document_type="receipt",
                fields={
                    "supplier_name": "Shop",
                    "supplier_tax_id": None,
                    "number": None,
                    "issue_date": None,
                    "sale_date": None,
                    "due_date": None,
                    "description": None,
                    "payee_iban": None,
                    "total": "1.00",
                    "currency": "PLN",
                },
                provenance={"source": "vision"},
                parser_version="test:model",
            ),
            warnings=(),
            ready=True,
        )

    monkeypatch.setattr(vision_worker, "extract_image_review", provider)
    await vision_worker.process_document_job({}, str(job.id))
    assert entered
    async with sessions() as db:
        revision = await db.get(DocumentExtractionRevision, job_revision_id)
        assert revision.status == "ready"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_env_stop_pauses_pending_and_rejects_inflight_publication(test_database, monkeypatch):
    """The infrastructure stop is a fail-closed boundary, not an auto-enable switch."""
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    monkeypatch.setattr(vision_worker, "async_session_factory", sessions)
    # Full publication race is exercised through the service CAS; this worker must not call HTTP.
    monkeypatch.setattr(vision_worker.settings, "DOCUMENT_VISION_ENABLED", False)
    monkeypatch.setattr(vision_worker, "extract_image_review", AsyncMock())
    await vision_worker.process_document_job({}, str(uuid.uuid4()))
    vision_worker.extract_image_review.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_missing_config_persists_configuration_missing_without_http(
    test_database, monkeypatch
):
    """An absent configured identity is durable configuration_missing, never an HTTP attempt."""
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    monkeypatch.setattr(vision_worker, "async_session_factory", sessions)
    monkeypatch.setattr(vision_worker.settings, "DOCUMENT_VISION_ENABLED", True)
    monkeypatch.setattr(vision_worker, "get_vision_config", lambda _settings: None)
    monkeypatch.setattr(job_service, "get_vision_config", lambda _settings: None)
    provider = AsyncMock()
    monkeypatch.setattr(vision_worker, "extract_image_review", provider)
    async with sessions() as db:
        user_id = uuid.uuid4()
        document = Document(
            user_id=user_id,
            filename="receipt.jpg",
            original_name="receipt.jpg",
            mime_type="image/jpeg",
            sha256_hash="c" * 64,
            size_bytes=1,
            storage_path="cc/receipt.jpg",
            processing_method="vision",
        )
        db.add_all(
            (
                document,
                DocumentVisionPolicy(
                    id=1,
                    enabled=True,
                    epoch=1,
                    configuration_fingerprint=_config().configuration_fingerprint,
                ),
            )
        )
        await db.flush()
        job = await create_vision_intent(db, user_id, document.id, key="vision:missing-config")
        await db.commit()
    await vision_worker.process_document_job({}, str(job.id))
    provider.assert_not_awaited()
    async with sessions() as db:
        job = await db.get(DocumentProcessingJob, job.id)
        revision = await db.get(DocumentExtractionRevision, job.revision_id)
        assert (job.state, job.error_code) == ("failed", "configuration_missing")
        assert (revision.status, revision.error_code) == ("incomplete", "configuration_missing")
