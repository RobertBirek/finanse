"""Observe PostgreSQL lock waits in both admission orders; never guess with sleeps."""

import asyncio
import hashlib
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.documents.receipt_read_config import get_receipt_read_config
from app.documents.receipt_read_models import ReceiptReadJob, ReceiptReadReservation
from app.documents.receipt_read_schemas import ReceiptReadCancel
from app.finance.categorization_context import CategorizationError
from tests.test_documents.fixtures import valid_jpeg_bytes
from tests.test_documents.test_receipt_read_worker import worker_ready
from tests.test_finance.test_categorization_races import wait_for_database_lock

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("first_operation", ["cancel", "reserve"])
async def test_cancel_and_dispatch_both_lock_admissions(
    db_session, monkeypatch, tmp_path, first_operation
):
    from app.documents.receipt_read_jobs import (
        ReceiptReadPrepared,
        claim_receipt_read,
        reserve_receipt_read_dispatch,
    )
    from app.finance.receipt_read_service import cancel_receipt_read

    r, ident = await worker_ready(db_session, monkeypatch, tmp_path)
    now = datetime.now(UTC)
    config = get_receipt_read_config(settings)
    claim = await claim_receipt_read(db_session, ident, now=now, config=config)
    await db_session.commit()
    jpeg = valid_jpeg_bytes()
    prepared = ReceiptReadPrepared(jpeg, hashlib.sha256(jpeg).hexdigest(), 10000)
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    admitted, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids = []
    outcomes = {}

    async def operation(db, which):
        if which == "reserve":
            outcomes[which] = await reserve_receipt_read_dispatch(
                db, claim, prepared, now=now, config=config
            )
        else:
            try:
                result = await cancel_receipt_read(
                    db,
                    r.owner,
                    r.bill_id,
                    ident,
                    ReceiptReadCancel(expected_version=2),
                    idempotency_key="barrier-cancel",
                )
                outcomes[which] = result.state
            except CategorizationError as e:
                outcomes[which] = e.code
                await db.rollback()

    async def first():
        async with sessions() as db:
            await operation(db, first_operation)
            admitted.set()
            await release.wait()
            await db.commit()

    async def second():
        await admitted.wait()
        async with sessions() as db:
            pids.append(await db.scalar(text("SELECT pg_backend_pid()")))
            waiting.set()
            await operation(db, "reserve" if first_operation == "cancel" else "cancel")
            await db.commit()

    a, b = asyncio.create_task(first()), asyncio.create_task(second())
    try:
        await asyncio.wait_for(waiting.wait(), 10)
        await wait_for_database_lock(db_session, pids[0])
        assert not b.done()
    finally:
        release.set()
        results = await asyncio.wait_for(asyncio.gather(a, b, return_exceptions=True), 15)
    assert not any(isinstance(v, BaseException) for v in results), results
    count = await db_session.scalar(select(func.count()).select_from(ReceiptReadReservation))
    if first_operation == "cancel":
        assert outcomes == {"cancel": "cancelled", "reserve": False} and count == 0
    else:
        assert outcomes == {"reserve": True, "cancel": "read_dispatched"} and count == 1


@pytest.mark.parametrize("first_operation", ["policy", "reserve"])
async def test_policy_stop_and_dispatch_both_admissions(
    db_session, monkeypatch, tmp_path, first_operation
):
    from app.documents.receipt_read_jobs import (
        ReceiptReadPrepared,
        claim_receipt_read,
        reserve_receipt_read_dispatch,
    )
    from app.documents.receipt_read_policy import set_receipt_read_policy

    _, ident = await worker_ready(db_session, monkeypatch, tmp_path)
    now = datetime.now(UTC)
    config = get_receipt_read_config(settings)
    claim = await claim_receipt_read(db_session, ident, now=now, config=config)
    await db_session.commit()
    jpeg = valid_jpeg_bytes()
    prepared = ReceiptReadPrepared(jpeg, hashlib.sha256(jpeg).hexdigest(), 10000)
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    admitted, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids = []
    outcomes = {}

    async def operation(db, which):
        if which == "reserve":
            outcomes[which] = await reserve_receipt_read_dispatch(
                db, claim, prepared, now=now, config=config
            )
        else:
            await set_receipt_read_policy(
                db, enabled=False, expected_epoch=1, config=None, performed_by="synthetic-barrier"
            )

    async def first():
        async with sessions() as db:
            await operation(db, first_operation)
            admitted.set()
            await release.wait()
            await db.commit()

    async def second():
        await admitted.wait()
        async with sessions() as db:
            pids.append(await db.scalar(text("SELECT pg_backend_pid()")))
            waiting.set()
            await operation(db, "reserve" if first_operation == "policy" else "policy")
            await db.commit()

    a, b = asyncio.create_task(first()), asyncio.create_task(second())
    try:
        await asyncio.wait_for(waiting.wait(), 10)
        await wait_for_database_lock(db_session, pids[0])
        assert not b.done()
    finally:
        release.set()
        results = await asyncio.wait_for(asyncio.gather(a, b, return_exceptions=True), 15)
    assert not any(isinstance(v, BaseException) for v in results), results
    count = await db_session.scalar(select(func.count()).select_from(ReceiptReadReservation))
    job = await db_session.get(ReceiptReadJob, ident, populate_existing=True)
    if first_operation == "policy":
        assert outcomes["reserve"] is False and count == 0 and job.state == "paused"
    else:
        assert outcomes["reserve"] is True and count == 1 and job.state == "superseded"


@pytest.mark.parametrize("kind", ["attach_source", "header", "draft"])
@pytest.mark.parametrize("first_operation", ["import", "other"])
async def test_import_source_attach_header_and_draft_both_admissions(
    db_session, monkeypatch, tmp_path, kind, first_operation
):
    from app.documents.receipt_read_schemas import (
        ReceiptReadImport,
        ReceiptReadImportPreviewRequest,
    )
    from app.finance.bills import attach_source, update_bill
    from app.finance.bills_schemas import BillUpdate, MutationContext
    from app.finance.receipt_items import save_receipt_draft
    from app.finance.receipt_read_import import import_receipt_read, preview_receipt_read_import
    from app.finance.receipt_read_models import ReceiptReadLineage
    from app.finance.receipt_schemas import ReceiptBody, ReceiptDraftSave
    from tests.test_finance.test_receipt_read_import import accepted

    r, ident = await accepted(db_session, monkeypatch, tmp_path)
    p = await preview_receipt_read_import(
        db_session,
        r.owner,
        r.bill_id,
        ReceiptReadImportPreviewRequest(job_id=ident, expected_state_version=0),
    )
    await db_session.commit()
    data = ReceiptReadImport(
        job_id=ident,
        expected_state_version=0,
        expected_import_snapshot=p.import_snapshot,
        confirmed_replace=True,
    )
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    admitted, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids = []
    outcomes = {}

    async def operation(db, which):
        try:
            if which == "import":
                await import_receipt_read(
                    db, r.owner, r.bill_id, data, idempotency_key="race-import"
                )
            elif kind == "attach_source":
                await attach_source(
                    db,
                    r.owner,
                    r.bill_id,
                    r.document_id,
                    1,
                    context=MutationContext(idempotency_key="race-source"),
                )
            elif kind == "header":
                await update_bill(
                    db,
                    r.owner,
                    r.bill_id,
                    BillUpdate(expected_version=1, description="Changed"),
                    context=MutationContext(idempotency_key="race-header"),
                )
            else:
                await save_receipt_draft(
                    db,
                    r.owner,
                    r.bill_id,
                    ReceiptDraftSave(
                        expected_version=0, expected_bill_version=1, body=ReceiptBody()
                    ),
                    idempotency_key="race-manual-draft",
                )
            outcomes[which] = "applied"
        except CategorizationError:
            outcomes[which] = "conflict"
            await db.rollback()

    async def first():
        async with sessions() as db:
            await operation(db, first_operation)
            admitted.set()
            await release.wait()
            await db.commit()

    async def second():
        await admitted.wait()
        async with sessions() as db:
            # Warm metadata must be refreshed after the competing commit.
            from app.finance.models import FinancialDocument

            await db.get(FinancialDocument, r.bill_id)
            pids.append(await db.scalar(text("SELECT pg_backend_pid()")))
            waiting.set()
            await operation(db, "import" if first_operation == "other" else "other")
            await db.commit()

    a, b = asyncio.create_task(first()), asyncio.create_task(second())
    try:
        await asyncio.wait_for(waiting.wait(), 10)
        await wait_for_database_lock(db_session, pids[0])
        assert not b.done()
    finally:
        release.set()
        results = await asyncio.wait_for(asyncio.gather(a, b, return_exceptions=True), 15)
    assert not any(isinstance(v, BaseException) for v in results), results
    assert outcomes[first_operation] == "applied"
    if first_operation == "other":
        assert outcomes["import"] == "conflict"
    elif kind == "draft":
        assert outcomes["other"] == "conflict"
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadLineage)) == (
        1 if first_operation == "import" else 0
    )


async def test_two_owners_cannot_overrun_global_daily_quota(db_session, monkeypatch, tmp_path):
    from app.documents.receipt_read_jobs import (
        ReceiptReadPrepared,
        claim_receipt_read,
        reserve_receipt_read_dispatch,
    )
    from app.documents.receipt_read_models import ReceiptReadUsage

    _, first_id = await worker_ready(db_session, monkeypatch, tmp_path)
    _, second_id = await worker_ready(db_session, monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "DOCUMENT_RECEIPT_ITEMS_DAILY_CALL_LIMIT_GLOBAL", 1)
    now = datetime.now(UTC)
    config = get_receipt_read_config(settings)
    claims = []
    for ident in [first_id, second_id]:
        claims.append(await claim_receipt_read(db_session, ident, now=now, config=config))
        await db_session.commit()
    jpeg = valid_jpeg_bytes()
    prepared = ReceiptReadPrepared(jpeg, hashlib.sha256(jpeg).hexdigest(), 10000)
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    admitted, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids = []
    outcomes = []

    async def first():
        async with sessions() as db:
            outcomes.append(
                await reserve_receipt_read_dispatch(db, claims[0], prepared, now=now, config=config)
            )
            admitted.set()
            await release.wait()
            await db.commit()

    async def second():
        await admitted.wait()
        async with sessions() as db:
            pids.append(await db.scalar(text("SELECT pg_backend_pid()")))
            waiting.set()
            outcomes.append(
                await reserve_receipt_read_dispatch(db, claims[1], prepared, now=now, config=config)
            )
            await db.commit()

    a, b = asyncio.create_task(first()), asyncio.create_task(second())
    try:
        await asyncio.wait_for(waiting.wait(), 10)
        await wait_for_database_lock(db_session, pids[0])
        assert not b.done()
    finally:
        release.set()
        results = await asyncio.wait_for(asyncio.gather(a, b, return_exceptions=True), 15)
    assert not any(isinstance(v, BaseException) for v in results), results
    assert outcomes == [True, False]
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadReservation)) == 1
    assert (
        await db_session.scalar(
            select(ReceiptReadUsage.reserved_calls).where(ReceiptReadUsage.scope_key == "global")
        )
        == 1
    )
