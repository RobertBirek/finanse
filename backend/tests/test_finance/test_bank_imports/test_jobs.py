from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.finance.imports import jobs as import_jobs
from app.finance.imports.contracts import ImportFailure
from app.finance.imports.errors import ImportError
from app.finance.imports.jobs import claim_import_job, finish_import_job, request_prepare
from app.finance.imports.models import (
    ImportBatch,
    ImportDecision,
    ImportEvidence,
    ImportGroup,
    ImportGroupRow,
    ImportJob,
    ImportRevision,
    ImportRow,
    ImportSource,
)
from app.finance.imports.service import get_batch, list_rows
from app.finance.models import FinanceCommandReceipt, Posting
from app.identity.models import User
from tests.test_finance.test_bank_imports.factories import (
    ledger_snapshot,
    ready_statement,
    seed_legacy_transfer,
)
from tests.test_finance.test_bank_imports.test_contracts import parsed_statement

pytestmark = pytest.mark.integration


async def prepared_source(db: AsyncSession, owner: User):
    batch_id = await ready_statement(db, owner.id, parsed_statement())
    batch = await get_batch(db, owner.id, batch_id)
    assert batch is not None
    job = await request_prepare(db, owner.id, batch.sources[0].id, key="synthetic-prepare")
    return batch, job


async def test_same_prepare_key_has_one_durable_revision_and_job(
    db_session: AsyncSession, owner: User
) -> None:
    batch, first = await prepared_source(db_session, owner)
    again = await request_prepare(
        db_session, owner.id, batch.sources[0].id, key="synthetic-prepare"
    )
    assert first.id == again.id and first.revision_id == again.revision_id
    assert await db_session.scalar(select(func.count()).select_from(ImportJob)) == 1
    assert await db_session.scalar(select(func.count()).select_from(ImportRevision)) == 2


async def test_distinct_keys_coalesce_while_one_read_is_active(
    db_session: AsyncSession, owner: User
) -> None:
    batch, first = await prepared_source(db_session, owner)
    again = await request_prepare(db_session, owner.id, batch.sources[0].id, key="another-prepare")
    assert again.id == first.id
    assert await db_session.scalar(select(func.count()).select_from(ImportJob)) == 1


async def test_prepare_is_owner_scoped(
    db_session: AsyncSession, owner: User, other_owner: User
) -> None:
    batch, _job = await prepared_source(db_session, owner)
    with pytest.raises(ImportError) as error:
        await request_prepare(db_session, other_owner.id, batch.sources[0].id, key="foreign-key")
    assert error.value.http_status == 404


async def test_prepare_key_cannot_be_reused_for_another_source(
    db_session: AsyncSession, owner: User
) -> None:
    await prepared_source(db_session, owner)
    second_id = await ready_statement(db_session, owner.id, parsed_statement())
    batch = await get_batch(db_session, owner.id, second_id)
    assert batch is not None
    with pytest.raises(ImportError) as error:
        await request_prepare(db_session, owner.id, batch.sources[0].id, key="synthetic-prepare")
    assert error.value.code == "idempotency_key_reused"


async def test_job_has_only_one_live_claim_and_duplicate_publication_is_noop(
    db_session: AsyncSession, owner: User
) -> None:
    batch, job = await prepared_source(db_session, owner)
    now = datetime.now(UTC)
    claim = await claim_import_job(db_session, job.id, now)
    assert claim is not None and claim.attempt == 1
    assert await claim_import_job(db_session, job.id, now) is None
    before = await ledger_snapshot(db_session)
    assert await finish_import_job(db_session, claim, parsed_statement()) is True
    assert await finish_import_job(db_session, claim, parsed_statement()) is False
    assert await ledger_snapshot(db_session) == before
    restored = await get_batch(db_session, owner.id, batch.id)
    assert restored is not None and restored.sources[0].processing_state == "ready"
    # prepared_source already has a successful revision: this job is a reparse,
    # even when no row has been committed. Publication must preserve that revision.
    assert restored.sources[0].current_revision_id == batch.sources[0].current_revision_id
    assert restored.sources[0].candidate_revision_id == claim.revision_id
    assert "reparse_requires_comparison" in restored.sources[0].warnings
    page = await list_rows(db_session, owner.id, batch.id, source_id=None, offset=0, limit=100)
    assert page.total == 2


async def test_stale_worker_cannot_publish_after_lease_recovery(
    db_session: AsyncSession, owner: User
) -> None:
    _batch, job = await prepared_source(db_session, owner)
    old = await claim_import_job(db_session, job.id, datetime.now(UTC) - timedelta(days=1))
    assert old is not None
    current = await claim_import_job(db_session, job.id, datetime.now(UTC))
    assert current is not None and current.attempt == 2 and current.lease_token != old.lease_token
    assert await finish_import_job(db_session, old, parsed_statement()) is False
    assert await finish_import_job(db_session, current, parsed_statement()) is True


async def test_expired_unrecovered_lease_cannot_publish(
    db_session: AsyncSession, owner: User
) -> None:
    _batch, job = await prepared_source(db_session, owner)
    claim = await claim_import_job(db_session, job.id, datetime.now(UTC) - timedelta(days=1))
    assert claim is not None
    assert await finish_import_job(db_session, claim, parsed_statement()) is False


async def test_retry_preserves_revision_and_backoff_then_has_a_finite_attempt_limit(
    db_session: AsyncSession,
    owner: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FINANCE_IMPORT_MAX_ATTEMPTS", 2)
    _batch, job = await prepared_source(db_session, owner)
    claim = await claim_import_job(db_session, job.id, datetime.now(UTC))
    assert claim is not None
    assert await finish_import_job(
        db_session, claim, ImportFailure("source_unavailable", retryable=True)
    )
    record = await db_session.get(ImportJob, job.id)
    assert record is not None and record.state == "queued" and record.next_attempt_at is not None
    assert await claim_import_job(db_session, job.id, datetime.now(UTC)) is None
    record.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()
    retry = await claim_import_job(db_session, job.id, datetime.now(UTC))
    assert retry is not None and retry.revision_id == claim.revision_id and retry.attempt == 2
    assert await finish_import_job(
        db_session, retry, ImportFailure("source_unavailable", retryable=True)
    )
    await db_session.refresh(record)
    assert record.state == "error"


async def test_required_failed_check_is_ready_but_financially_blocked(
    db_session: AsyncSession, owner: User
) -> None:
    batch, job = await prepared_source(db_session, owner)
    result = parsed_statement()
    result = result.model_copy(
        update={"checks": [result.checks[0].model_copy(update={"result": "failed"})]}
    )
    claim = await claim_import_job(db_session, job.id, datetime.now(UTC))
    assert claim is not None and await finish_import_job(db_session, claim, result)
    restored = await get_batch(db_session, owner.id, batch.id)
    assert restored is not None
    assert (
        restored.sources[0].processing_state == "ready"
        and restored.sources[0].validation_state == "blocked"
    )


async def test_publication_does_not_wait_on_owner_lock_while_holding_job_lock(
    db_session: AsyncSession,
    owner: User,
    test_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    batch, job = await prepared_source(db_session, owner)
    owner_id = owner.id
    claim = await claim_import_job(db_session, job.id, datetime.now(UTC))
    assert claim is not None
    await db_session.commit()
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    async with sessions() as blocker:
        await blocker.execute(
            select(func.pg_advisory_xact_lock(func.hashtext(f"bill-allocation:{owner_id}")))
        )
        started = asyncio.Event()
        original_lock = import_jobs.lock_document_mutations

        async def observed_owner_lock(db, user_id):
            started.set()
            await original_lock(db, user_id)

        monkeypatch.setattr(import_jobs, "lock_document_mutations", observed_owner_lock)

        async def publish():
            async with sessions() as publisher:
                value = await finish_import_job(publisher, claim, parsed_statement())
                await publisher.commit()
                return value

        task = asyncio.create_task(publish())
        try:
            await started.wait()
            async with sessions() as probe:
                available = await probe.scalar(
                    select(ImportJob.id)
                    .where(ImportJob.id == job.id)
                    .with_for_update(skip_locked=True)
                )
                assert available == job.id
            await blocker.rollback()
            assert await asyncio.wait_for(task, timeout=10)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    assert batch.id is not None


async def test_reparse_keeps_paid_evidence_and_decision_and_requires_explicit_comparison(
    db_session: AsyncSession,
    owner: User,
) -> None:
    await seed_legacy_transfer(db_session, owner.id)
    batch_id = await ready_statement(db_session, owner.id, parsed_statement())
    row = await db_session.scalar(
        select(ImportRow).where(ImportRow.batch_id == batch_id).order_by(ImportRow.ordinal)
    )
    assert row is not None
    source = await db_session.get(ImportSource, row.source_id)
    assert source is not None
    previous_revision = source.current_revision_id
    posting = await db_session.scalar(select(Posting))
    assert posting is not None
    group = ImportGroup(user_id=owner.id, batch_id=batch_id, state="committed")
    receipt = FinanceCommandReceipt(
        user_id=owner.id,
        action="synthetic-import",
        key="old",
        request_hash="a" * 64,
        response_json={},
    )
    db_session.add_all([group, receipt])
    await db_session.flush()
    evidence = ImportEvidence(
        user_id=owner.id,
        batch_id=batch_id,
        group_id=group.id,
        row_id=row.id,
        transaction_id=posting.transaction_id,
        posting_id=posting.id,
        receipt_id=receipt.id,
        component="whole",
        attributed_source_amount=-100,
    )
    decision = ImportDecision(
        user_id=owner.id,
        batch_id=batch_id,
        group_id=group.id,
        version=1,
        data={"action": "link", "row_ids": [str(row.id)]},
    )
    db_session.add_all(
        [
            evidence,
            decision,
            ImportGroupRow(user_id=owner.id, batch_id=batch_id, group_id=group.id, row_id=row.id),
        ]
    )
    await db_session.flush()
    before = await ledger_snapshot(db_session)
    evidence_id, decision_id, row_id = evidence.id, decision.id, row.id
    job = await request_prepare(db_session, owner.id, source.id, key="reparse-paid")
    claim = await claim_import_job(db_session, job.id, datetime.now(UTC))
    assert claim is not None and await finish_import_job(db_session, claim, parsed_statement())
    await db_session.refresh(source)
    assert source.current_revision_id == previous_revision
    assert source.validation_state == "needs_review"
    revision = await db_session.get(ImportRevision, claim.revision_id)
    assert revision is not None and "reparse_requires_comparison" in revision.warnings
    assert await db_session.get(ImportEvidence, evidence_id) is not None
    assert await db_session.get(ImportDecision, decision_id) is not None
    page = await list_rows(db_session, owner.id, batch_id, source_id=source.id, offset=0, limit=100)
    assert row_id in {item.id for item in page.items} and page.total == 2
    assert await ledger_snapshot(db_session) == before


async def test_archived_batch_refuses_new_preparation_and_discards_inflight_result(
    db_session: AsyncSession,
    owner: User,
) -> None:
    batch, job = await prepared_source(db_session, owner)
    claim = await claim_import_job(db_session, job.id, datetime.now(UTC))
    assert claim is not None
    record = await db_session.get(ImportBatch, batch.id)
    assert record is not None
    record.archived_at = datetime.now(UTC)
    await db_session.flush()
    assert await finish_import_job(db_session, claim, parsed_statement()) is False
    with pytest.raises(ImportError) as error:
        await request_prepare(db_session, owner.id, batch.sources[0].id, key="archived")
    assert error.value.code == "import_archived"
