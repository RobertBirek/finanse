import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.main  # noqa: F401 - register complete metadata for integration schema lifecycle
from app.documents.job_models import (
    DocumentVisionPolicy,
    DocumentVisionUsage,
)
from app.documents.job_service import (
    claim_processing_job,
    create_vision_intent,
    reserve_vision_call,
)
from app.documents.models import Document, DocumentExtractionRevision
from app.documents.vision_config import VisionConfig


def _config() -> VisionConfig:
    return VisionConfig("test", "https://vision.example.test/v1", "model", "secret", "p1", "s1")


async def _vision_job(db_session):
    user_id = uuid.uuid4()
    document = Document(
        user_id=user_id,
        filename="receipt.jpg",
        original_name="receipt.jpg",
        mime_type="image/jpeg",
        sha256_hash="a" * 64,
        size_bytes=1,
        storage_path="aa/receipt.jpg",
        processing_method="vision",
    )
    db_session.add_all(
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
    await db_session.flush()
    revision = DocumentExtractionRevision(
        user_id=user_id,
        document_id=document.id,
        revision=1,
        status="pending",
        data={
            "document_type": "other",
            "fields": {},
            "provenance": {},
            "parser_version": None,
        },
        field_provenance={},
        input_method="image",
    )
    db_session.add(revision)
    await db_session.flush()
    job = await create_vision_intent(db_session, user_id, document.id, key="vision:1")
    await db_session.commit()
    return user_id, document.id, revision.id, job.id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_duplicate_claim_reserves_one_call(test_database, monkeypatch):
    """A duplicate delivery must not turn one lease into two billable sends."""
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    monkeypatch.setattr(
        __import__("app.documents.job_service", fromlist=["settings"]).settings,
        "DOCUMENT_VISION_ENABLED",
        True,
    )
    async with sessions() as db:
        _, _, _, job_id = await _vision_job(db)
    now = datetime(2026, 10, 31, tzinfo=UTC)
    async with sessions() as first, sessions() as second:
        claim = await claim_processing_job(first, job_id, now=now)
        await first.commit()
        duplicate = await claim_processing_job(second, job_id, now=now)
        assert claim is not None
        assert duplicate is None
    async with sessions() as db:
        assert await reserve_vision_call(db, claim, now=now, config=_config()) is True
        await db.commit()
    async with sessions() as db:
        assert await reserve_vision_call(db, claim, now=now, config=_config()) is False
        usage = (await db.execute(select(DocumentVisionUsage))).scalar_one()
        assert usage.reserved_calls == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_global_concurrency_and_user_daily_limit_atomic(test_database, monkeypatch):
    """Admission and UTC usage reservation are durable and atomic."""
    from app.documents import job_service

    monkeypatch.setattr(job_service.settings, "DOCUMENT_VISION_CONCURRENCY", 1)
    monkeypatch.setattr(job_service.settings, "DOCUMENT_VISION_DAILY_CALL_LIMIT_PER_USER", 1)
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    async with sessions() as db:
        _, _, _, first_id = await _vision_job(db)
        # A second document has a distinct durable job but shares the global slot.
        user_id = uuid.uuid4()
        document = Document(
            user_id=user_id,
            filename="two.jpg",
            original_name="two.jpg",
            mime_type="image/jpeg",
            sha256_hash="b" * 64,
            size_bytes=1,
            storage_path="bb/two.jpg",
            processing_method="vision",
        )
        db.add(document)
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
        second = await create_vision_intent(db, user_id, document.id, key="vision:2")
        await db.commit()
    now = datetime(2026, 10, 31, tzinfo=UTC)
    async with sessions() as db:
        assert await claim_processing_job(db, first_id, now=now) is not None
        await db.commit()
    async with sessions() as db:
        assert await claim_processing_job(db, second.id, now=now) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_usage_failure_prevents_http(test_database, monkeypatch):
    """A failed quota reservation is fail-closed before any provider boundary."""
    from app.documents import job_service

    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    monkeypatch.setattr(job_service.settings, "DOCUMENT_VISION_ENABLED", True)
    async with sessions() as db:
        _, _, _, job_id = await _vision_job(db)
    now = datetime(2026, 10, 31, tzinfo=UTC)
    async with sessions() as db:
        claim = await claim_processing_job(db, job_id, now=now)
        await db.commit()
    assert claim is not None
    monkeypatch.setattr(
        job_service,
        "_reserve_usage",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db")),
    )
    async with sessions() as db:
        assert await reserve_vision_call(db, claim, now=now, config=_config()) is False
