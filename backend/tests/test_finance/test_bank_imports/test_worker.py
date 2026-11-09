from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.documents import service as document_service
from app.documents.import_storage import store_import_document
from app.finance.imports import storage
from app.finance.imports import worker as import_worker
from app.finance.imports.jobs import claim_import_job, request_prepare
from app.finance.imports.models import ImportJob, ImportRevision, ImportSource
from app.finance.imports.service import create_batch
from app.finance.imports.storage import attach_source
from app.identity.models import User
from tests.test_finance.test_bank_imports.factories import ledger_snapshot, text_pdf_bytes

pytestmark = pytest.mark.integration


class UnavailableQueue:
    async def enqueue_job(self, *args: object, **kwargs: object) -> object:
        raise OSError("synthetic-redis-unavailable")


async def test_durable_prepare_survives_redis_failure_and_worker_parses_without_database_transaction(
    db_session: AsyncSession,
    owner: User,
    test_database,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(document_service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        import_worker,
        "async_session_factory",
        async_sessionmaker(test_database, expire_on_commit=False),
    )
    content = text_pdf_bytes("Citi Handlowy\nSynthetic unsupported statement")
    document, _ = await store_import_document(
        db_session, owner.id, filename="source.pdf", content=content
    )
    batch = await create_batch(db_session, owner.id, "statement")
    attached = await attach_source(db_session, owner.id, batch.id, document.id)
    job = await request_prepare(db_session, owner.id, attached.source.id, key="durable-test")
    owner_id = owner.id
    before = await ledger_snapshot(db_session)
    await db_session.commit()
    await import_worker.dispatch_import_jobs({"redis": UnavailableQueue()})
    async with async_sessionmaker(test_database)() as probe:
        record = await probe.get(ImportJob, job.id)
        assert record is not None and record.state == "queued"
    extract = storage.extract_pdf_pages

    def without_database_transaction(content, limits):
        assert test_database.pool.checkedout() == 0
        return extract(content, limits)

    monkeypatch.setattr(storage, "extract_pdf_pages", without_database_transaction)
    await import_worker.process_import_job({}, str(job.id))
    async with async_sessionmaker(test_database)() as probe:
        record = await probe.get(ImportJob, job.id)
        source = await probe.get(ImportSource, attached.source.id)
        revision = await probe.get(ImportRevision, job.revision_id)
        assert (
            record is not None
            and record.state == "unsupported"
            and record.error_code == "bank_unsupported"
        )
        assert (
            source is not None
            and source.user_id == owner_id
            and source.validation_state == "blocked"
        )
        assert revision is not None and revision.result is None
        assert await ledger_snapshot(probe) == before


async def test_dispatcher_sends_only_ids_with_stable_transport_identity(
    db_session: AsyncSession,
    owner: User,
    test_database,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(document_service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        import_worker,
        "async_session_factory",
        async_sessionmaker(test_database, expire_on_commit=False),
    )
    document, _ = await store_import_document(
        db_session,
        owner.id,
        filename="source.pdf",
        content=text_pdf_bytes("Synthetic unknown layout"),
    )
    batch = await create_batch(db_session, owner.id, "statement")
    attached = await attach_source(db_session, owner.id, batch.id, document.id)
    job = await request_prepare(db_session, owner.id, attached.source.id, key="dispatch-test")
    await db_session.commit()
    deliveries = []

    class Queue:
        async def enqueue_job(self, *args, **kwargs):
            deliveries.append((args, kwargs))

    await import_worker.dispatch_import_jobs({"redis": Queue()})
    assert deliveries == [
        (("process_import_job", str(job.id)), {"_job_id": f"finance-import:{job.id}"})
    ]


async def test_invalid_worker_id_is_noop() -> None:
    await import_worker.process_import_job({}, "not-a-uuid")


def test_global_worker_registers_import_delivery_and_recovery_separately() -> None:
    from app.worker import WorkerSettings

    assert any(
        getattr(item, "coroutine", None) is import_worker.process_import_job
        for item in WorkerSettings.functions
    )
    assert any(
        item.coroutine is import_worker.dispatch_import_jobs for item in WorkerSettings.cron_jobs
    )


async def test_exhausted_crashed_job_is_terminal_instead_of_redelivered_forever(
    db_session: AsyncSession,
    owner: User,
    test_database,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FINANCE_IMPORT_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(document_service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        import_worker,
        "async_session_factory",
        async_sessionmaker(test_database, expire_on_commit=False),
    )
    document, _ = await store_import_document(
        db_session, owner.id, filename="source.pdf", content=text_pdf_bytes("Synthetic table")
    )
    batch = await create_batch(db_session, owner.id, "statement")
    attached = await attach_source(db_session, owner.id, batch.id, document.id)
    job = await request_prepare(db_session, owner.id, attached.source.id, key="crash-limit")
    claim = await claim_import_job(db_session, job.id, datetime.now(UTC) - timedelta(days=1))
    assert claim is not None
    await db_session.commit()
    await import_worker.dispatch_import_jobs({"redis": UnavailableQueue()})
    async with async_sessionmaker(test_database)() as probe:
        record = await probe.get(ImportJob, job.id)
        source = await probe.get(ImportSource, attached.source.id)
        assert (
            record is not None
            and record.state == "error"
            and record.error_code == "attempts_exhausted"
        )
        assert source is not None and source.processing_state == "error"
