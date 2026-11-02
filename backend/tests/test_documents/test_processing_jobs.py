import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.main  # noqa: F401 - register complete metadata for integration schema lifecycle
from app.documents import service
from app.documents.job_models import (
    DocumentProcessingJob,
    DocumentVisionPolicy,
    DocumentVisionUsage,
)
from app.documents.job_service import (
    JobOutcome,
    claim_processing_job,
    create_vision_intent,
    finish_processing_job,
    recover_processing_jobs,
    reserve_vision_call,
)
from app.documents.models import Document, DocumentExtractionRevision
from app.documents.processing_policy import set_vision_policy
from app.documents.vision_config import VisionConfig
from app.finance.models import FinancialDocument, FinancialDocumentSource, Posting


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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_missing_vision_revision_terminalizes_its_document(db_session):
    document = Document(
        user_id=uuid.uuid4(),
        filename="malformed.jpg",
        original_name="malformed.jpg",
        mime_type="image/jpeg",
        sha256_hash="f" * 64,
        size_bytes=1,
        storage_path="ff/malformed.jpg",
        processing_method="vision",
    )
    db_session.add_all(
        (
            document,
            DocumentVisionPolicy(id=1, enabled=True, epoch=1),
        )
    )
    await db_session.flush()
    revision = DocumentExtractionRevision(
        user_id=document.user_id,
        document_id=document.id,
        revision=1,
        status="pending",
        data={"document_type": "other", "fields": {}, "provenance": {}, "parser_version": None},
        field_provenance={},
        input_method="image",
    )
    db_session.add(revision)
    await db_session.flush()
    job = DocumentProcessingJob(
        user_id=document.user_id,
        document_id=document.id,
        revision_id=revision.id,
        kind="vision",
        intent_key="malformed-revision",
        request_hash="malformed",
        state="pending",
    )
    db_session.add(job)
    await db_session.flush()
    # A corrupt legacy row is not creatable through the FK; simulate it only inside this rollback.
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        update(DocumentProcessingJob)
        .where(DocumentProcessingJob.id == job.id)
        .values(revision_id=uuid.uuid4())
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))

    assert (
        await claim_processing_job(db_session, job.id, now=datetime(2026, 11, 2, tzinfo=UTC))
        is None
    )
    assert (job.state, job.error_code, document.status) == ("failed", "revision_missing", "done")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_daily_limit_terminalizes_document_and_exposes_safe_summary(
    test_database, monkeypatch
):
    _vision_runtime(monkeypatch)
    from app.documents import job_service

    monkeypatch.setattr(job_service.settings, "DOCUMENT_VISION_DAILY_CALL_LIMIT_PER_USER", 1)
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    now = datetime(2026, 10, 31, tzinfo=UTC)
    async with sessions() as db:
        user_id, document_id, _, job_id = await _vision_job(db)
        db.add(DocumentVisionUsage(user_id=user_id, usage_date=now.date(), reserved_calls=1))
        await db.commit()
    async with sessions() as db:
        claim = await claim_processing_job(db, job_id, now=now)
        assert claim is not None
        revision_id = claim.revision_id
        assert revision_id is not None
        assert not await reserve_vision_call(db, claim, now=now, config=_config())
        await db.commit()
    async with sessions() as db:
        document = await db.get(Document, document_id)
        revision = await db.get(DocumentExtractionRevision, revision_id)
        job = await db.get(DocumentProcessingJob, job_id)
        summary = (await service.document_responses(db, user_id, [document]))[0].review
        assert document is not None and document.status == "done"
        assert (job.state, job.error_code) == ("failed", "vision_daily_limit")
        assert (revision.status, revision.error_code) == ("incomplete", "vision_daily_limit")
        assert summary is not None and (summary.status, summary.error_code) == (
            "incomplete",
            "vision_daily_limit",
        )


def _vision_runtime(monkeypatch) -> None:
    from app.documents import job_service

    monkeypatch.setattr(job_service.settings, "DOCUMENT_VISION_ENABLED", True)
    monkeypatch.setattr(job_service, "get_vision_config", lambda _settings: _config())


@pytest.mark.integration
@pytest.mark.asyncio
async def test_timeout_after_remote_acceptance_is_bounded(test_database, monkeypatch):
    """Each uncertain send consumes once; the bounded retry cannot create a third call."""
    _vision_runtime(monkeypatch)
    from app.documents import job_service

    monkeypatch.setattr(job_service.settings, "DOCUMENT_VISION_MAX_ATTEMPTS", 2)
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    start = datetime(2026, 10, 31, 23, 58, tzinfo=UTC)
    async with sessions() as db:
        _, _, _, job_id = await _vision_job(db)
    async with sessions() as db:
        first = await claim_processing_job(db, job_id, now=start)
        assert first is not None
        assert await reserve_vision_call(db, first, now=start, config=_config())
        assert not await reserve_vision_call(db, first, now=start, config=_config())
        assert await finish_processing_job(
            db, first, JobOutcome(error_code="provider_timeout", retryable=True), now=start
        )
        await db.commit()
    async with sessions() as db:
        second = await claim_processing_job(db, job_id, now=start.replace(minute=59))
        assert second is not None
        assert await reserve_vision_call(db, second, now=start.replace(minute=59), config=_config())
        assert await finish_processing_job(
            db,
            second,
            JobOutcome(error_code="provider_timeout", retryable=True),
            now=start.replace(minute=59),
        )
        await db.commit()
    async with sessions() as db:
        job = await db.get(DocumentProcessingJob, job_id)
        document = await db.get(Document, job.document_id)
        usage = (await db.execute(select(DocumentVisionUsage))).scalar_one()
        assert (job.state, job.attempt_count, usage.reserved_calls) == ("failed", 2, 2)
        assert document.status == "done"
        assert await claim_processing_job(db, job_id, now=start.replace(hour=1, day=1)) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_old_lease_result_cannot_replace_new_revision(test_database, monkeypatch):
    """A late provider result is superseded rather than replacing a human's newer revision."""
    _vision_runtime(monkeypatch)
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    now = datetime(2026, 10, 31, tzinfo=UTC)
    async with sessions() as db:
        user_id, document_id, _, job_id = await _vision_job(db)
    async with sessions() as db:
        claim = await claim_processing_job(db, job_id, now=now)
        assert claim is not None
        await db.commit()
    async with sessions() as db:
        db.add(
            DocumentExtractionRevision(
                user_id=user_id,
                document_id=document_id,
                revision=3,
                status="ready",
                data={
                    "document_type": "receipt",
                    "fields": {},
                    "provenance": {},
                    "parser_version": "human",
                },
                field_provenance={},
                input_method="image",
            )
        )
        await db.commit()
    async with sessions() as db:
        assert not await finish_processing_job(db, claim, JobOutcome(), now=now)
        await db.commit()
    async with sessions() as db:
        job = await db.get(DocumentProcessingJob, job_id)
        newest = (
            (
                await db.execute(
                    select(DocumentExtractionRevision)
                    .where(DocumentExtractionRevision.document_id == document_id)
                    .order_by(DocumentExtractionRevision.revision.desc())
                )
            )
            .scalars()
            .first()
        )
        assert (job.state, newest.revision, newest.data["parser_version"]) == (
            "superseded",
            3,
            "human",
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_approval_during_network_leaves_financial_document_and_postings_unchanged(
    test_database, monkeypatch
):
    """Publishing a vision review never alters an approved financial document or postings."""
    _vision_runtime(monkeypatch)
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    now = datetime(2026, 10, 31, tzinfo=UTC)
    async with sessions() as db:
        user_id, document_id, _, job_id = await _vision_job(db)
        financial = FinancialDocument(
            user_id=user_id,
            kind="receipt",
            supplier_name="Human",
            description="approved",
            total_minor=100,
            currency="PLN",
            review="approved",
        )
        db.add(financial)
        await db.flush()
        db.add(
            FinancialDocumentSource(
                user_id=user_id, financial_document_id=financial.id, document_id=document_id
            )
        )
        await db.commit()
    async with sessions() as db:
        claim = await claim_processing_job(db, job_id, now=now)
        assert claim is not None
        await db.commit()
    async with sessions() as db:
        before = (await db.execute(select(FinancialDocument))).scalar_one()
        before_snapshot = (
            before.id,
            before.review,
            before.supplier_name,
            before.total_minor,
            before.version,
            (await db.execute(select(Posting))).scalars().all(),
        )
        assert await finish_processing_job(
            db, claim, JobOutcome(error_code="invalid_model_output"), now=now
        )
        await db.commit()
    async with sessions() as db:
        after = (await db.execute(select(FinancialDocument))).scalar_one()
        document = await db.get(Document, document_id)
        assert (
            after.id,
            after.review,
            after.supplier_name,
            after.total_minor,
            after.version,
            (await db.execute(select(Posting))).scalars().all(),
        ) == before_snapshot
        assert document is not None and document.status == "done"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recovery_expiry_attempt_cap_is_terminal(test_database, monkeypatch):
    """Repeated expiry reaches a terminal job instead of endlessly requeueing it."""
    _vision_runtime(monkeypatch)
    from app.documents import job_service

    monkeypatch.setattr(job_service.settings, "DOCUMENT_VISION_MAX_ATTEMPTS", 2)
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    now = datetime(2026, 10, 31, tzinfo=UTC)
    async with sessions() as db:
        _, _, _, job_id = await _vision_job(db)
        first = await claim_processing_job(db, job_id, now=now)
        assert first is not None
        await db.commit()
    async with sessions() as db:
        assert await recover_processing_jobs(db, now=now.replace(minute=3), limit=10) == [job_id]
        await db.commit()
    async with sessions() as db:
        job = await db.get(DocumentProcessingJob, job_id)
        revision = await db.get(DocumentExtractionRevision, job.revision_id)
        assert (job.state, revision.status) == ("pending", "pending")
    async with sessions() as db:
        second = await claim_processing_job(db, job_id, now=now.replace(minute=3))
        assert second is not None
        await db.commit()
    async with sessions() as db:
        assert await recover_processing_jobs(db, now=now.replace(minute=6), limit=10) == []
        await db.commit()
    async with sessions() as db:
        job = await db.get(DocumentProcessingJob, job_id)
        revision = await db.get(DocumentExtractionRevision, job.revision_id)
        document = await db.get(Document, job.document_id)
        assert (job.state, job.attempt_count, job.error_code) == ("failed", 2, "attempts_exhausted")
        assert (revision.status, revision.error_code) == ("incomplete", "attempts_exhausted")
        assert document.status == "done"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_expired_unreclaimed_lease_cannot_publish(test_database, monkeypatch):
    """A response after its lease deadline cannot publish before recovery has run."""
    _vision_runtime(monkeypatch)
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    claimed_at = datetime(2026, 10, 31, tzinfo=UTC)
    async with sessions() as first:
        _, _, _, job_id = await _vision_job(first)
        claim = await claim_processing_job(first, job_id, now=claimed_at)
        assert claim is not None
        await first.commit()
    async with sessions() as second:
        assert not await finish_processing_job(
            second, claim, JobOutcome(error_code="late_result"), now=claimed_at.replace(minute=3)
        )
        await second.commit()
    async with sessions() as db:
        job = await db.get(DocumentProcessingJob, job_id)
        revision = await db.get(DocumentExtractionRevision, job.revision_id)
        assert (job.state, revision.status, revision.error_code) == (
            "processing",
            "processing",
            None,
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_policy_off_on_and_fingerprint_change_reject_old_lease(test_database, monkeypatch):
    """Neither re-enable nor a changed endpoint revives a pre-change lease."""
    _vision_runtime(monkeypatch)
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    now = datetime(2026, 10, 31, tzinfo=UTC)
    async with sessions() as db:
        _, _, _, job_id = await _vision_job(db)
        claim = await claim_processing_job(db, job_id, now=now)
        assert claim is not None
        await set_vision_policy(db, enabled=False, performed_by="test")
        await set_vision_policy(db, enabled=True, performed_by="test", config=_config())
        await db.commit()
    async with sessions() as db:
        assert not await reserve_vision_call(db, claim, now=now, config=_config())
        assert not await finish_processing_job(db, claim, JobOutcome(), now=now)
        await db.commit()
    changed = VisionConfig("test", "https://other.example.test/v1", "model", "secret", "p1", "s1")
    async with sessions() as db:
        renewed = await create_vision_intent(
            db, claim.user_id, claim.document_id, key="vision:new-epoch"
        )
        renewed_claim = await claim_processing_job(db, renewed.id, now=now)
        assert renewed_claim is not None
        assert not await reserve_vision_call(db, renewed_claim, now=now, config=changed)
        await db.commit()
    async with sessions() as db:
        policy = await db.get(DocumentVisionPolicy, 1)
        renewed = await db.get(DocumentProcessingJob, renewed.id)
        assert policy is not None
        assert policy.epoch > claim.policy_epoch
        assert policy.enabled
        assert policy.configuration_fingerprint == _config().configuration_fingerprint
        assert policy.configuration_fingerprint != changed.configuration_fingerprint
        assert (renewed.state, renewed.error_code) == ("paused", "vision_configuration_changed")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_usage_uses_utc_date_boundary(test_database, monkeypatch):
    """Calls either side of midnight are counted in separate UTC usage rows."""
    _vision_runtime(monkeypatch)
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    async with sessions() as db:
        user_id, _, _, first_id = await _vision_job(db)
        document = Document(
            user_id=user_id,
            filename="second.jpg",
            original_name="second.jpg",
            mime_type="image/jpeg",
            sha256_hash="z" * 64,
            size_bytes=1,
            storage_path="zz/second.jpg",
            processing_method="vision",
        )
        db.add(document)
        await db.flush()
        second = await create_vision_intent(db, user_id, document.id, key="vision:midnight")
        await db.commit()
    before = datetime(2026, 10, 31, 23, 59, tzinfo=UTC)
    after = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
    async with sessions() as db:
        first = await claim_processing_job(db, first_id, now=before)
        assert first is not None and await reserve_vision_call(
            db, first, now=before, config=_config()
        )
        await db.commit()
    async with sessions() as db:
        second_claim = await claim_processing_job(db, second.id, now=after)
        assert second_claim is not None and await reserve_vision_call(
            db, second_claim, now=after, config=_config()
        )
        await db.commit()
    async with sessions() as db:
        assert [
            (row.usage_date.isoformat(), row.reserved_calls)
            for row in (
                await db.execute(
                    select(DocumentVisionUsage).order_by(DocumentVisionUsage.usage_date)
                )
            ).scalars()
        ] == [("2026-10-31", 1), ("2026-11-01", 1)]
