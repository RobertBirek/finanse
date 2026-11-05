"""Real database and bounded HTTP transport. Restart never grants another export."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.documents.models import Document
from app.documents.receipt_read_config import get_receipt_read_config
from app.documents.receipt_read_models import (
    ReceiptReadExtraction,
    ReceiptReadJob,
    ReceiptReadReservation,
    ReceiptReadUsage,
)
from tests.test_documents.fixtures import valid_jpeg_bytes
from tests.test_documents.test_receipt_read_payload import payload_data
from tests.test_documents.test_vision_client import _response
from tests.test_finance.receipt_read_helpers import read_ready, start
from tests.test_finance.test_account_currency import client_for

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def worker_ready(db, monkeypatch, tmp_path):
    from app.documents import receipt_read_worker as w

    r = await read_ready(db, monkeypatch)
    doc = await db.get(Document, r.document_id)
    jpeg = valid_jpeg_bytes()
    doc.storage_path = "synthetic.jpg"
    doc.mime_type = "image/jpeg"
    doc.size_bytes = len(jpeg)
    doc.sha256_hash = hashlib.sha256(jpeg).hexdigest()
    (tmp_path / doc.storage_path).write_bytes(jpeg)
    await db.commit()
    monkeypatch.setattr(w, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        w, "async_session_factory", async_sessionmaker(db.bind, expire_on_commit=False)
    )
    async with client_for(db, r.owner) as client:
        response = await start(client, r)
        assert response.status_code == 200, response.text
    await db.commit()
    return r, uuid.UUID(response.json()["id"])


def bounded_http(monkeypatch, handler):
    from app.documents import receipt_read_client as c
    from app.openai_client import BoundedTransport

    monkeypatch.setattr(
        c,
        "_create_http_client",
        lambda config: httpx.AsyncClient(
            transport=BoundedTransport(
                httpx.MockTransport(handler), max_bytes=config.max_response_bytes
            ),
            follow_redirects=False,
            trust_env=False,
        ),
    )


async def test_timeout_redelivery_restart_never_resends_generation(
    db_session, monkeypatch, tmp_path
):
    from app.documents.receipt_read_jobs import recover_receipt_reads
    from app.documents.receipt_read_worker import process_receipt_read

    _, ident = await worker_ready(db_session, monkeypatch, tmp_path)
    calls = []

    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout("safe synthetic timeout", request=req)

    bounded_http(monkeypatch, handler)
    await process_receipt_read({}, str(ident))
    await process_receipt_read({}, str(ident))
    await recover_receipt_reads(db_session, now=datetime.now(UTC) + timedelta(hours=1), limit=100)
    await db_session.commit()
    await process_receipt_read({}, str(ident))
    job = await db_session.get(ReceiptReadJob, ident, populate_existing=True)
    assert len(calls) == 1 and job.state == "unknown" and job.dispatch_token
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadExtraction)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadReservation)) == 1
    assert (await db_session.scalars(select(ReceiptReadUsage.reserved_calls))).all() == [1, 1]


async def test_network_runs_only_after_marker_commit_and_result_is_immutable(
    db_session, monkeypatch, tmp_path
):
    from app.documents.receipt_read_worker import process_receipt_read

    _, ident = await worker_ready(db_session, monkeypatch, tmp_path)
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    calls = []

    async def handler(req):
        calls.append(req)
        async with sessions() as db:
            job = await db.scalar(
                select(ReceiptReadJob)
                .where(ReceiptReadJob.id == ident)
                .with_for_update(nowait=True)
            )
            assert job.state == "dispatched" and job.dispatch_token
            assert await db.scalar(select(func.count()).select_from(ReceiptReadReservation)) == 1
            assert await db.scalar(select(Document.id).with_for_update(nowait=True))
        return _response(payload_data())

    bounded_http(monkeypatch, handler)
    await process_receipt_read({}, str(ident))
    await process_receipt_read({}, str(ident))
    job = await db_session.get(ReceiptReadJob, ident, populate_existing=True)
    extraction = await db_session.scalar(select(ReceiptReadExtraction))
    assert len(calls) == 1 and job.state == "succeeded" and extraction.quality == "complete"
    assert extraction.payload_json["printed_total"] == "90.00"
    assert extraction.proposal_json["body"]["lines"][0]["category_id"] is None

    async with client_for(db_session, extraction.user_id) as client:
        result = await client.get(
            f"/api/finance/bills/{extraction.bill_id}/items/reads/{ident}/result"
        )
        assert result.status_code == 200, result.text
        assert result.json()["payload"]["printed_total"] == "90.00"


@pytest.mark.parametrize("change", ["policy", "env", "header", "detach"])
async def test_late_output_after_policy_change_never_becomes_ready(
    db_session, monkeypatch, tmp_path, change
):
    from app.documents.receipt_read_policy import set_receipt_read_policy
    from app.documents.receipt_read_worker import process_receipt_read
    from app.finance.models import FinancialDocument, FinancialDocumentSource

    r, ident = await worker_ready(db_session, monkeypatch, tmp_path)
    calls = []

    async def handler(req):
        calls.append(req)
        if change == "env":
            monkeypatch.setattr(settings, "DOCUMENT_RECEIPT_ITEMS_ENABLED", False)
        else:
            if change == "policy":
                await set_receipt_read_policy(
                    db_session,
                    enabled=False,
                    expected_epoch=1,
                    config=None,
                    performed_by="synthetic-test",
                )
            if change == "header":
                await db_session.execute(
                    update(FinancialDocument)
                    .where(FinancialDocument.id == r.bill_id)
                    .values(total_minor=9001)
                )
            if change == "detach":
                row = await db_session.scalar(
                    select(FinancialDocumentSource).where(
                        FinancialDocumentSource.document_id == r.document_id
                    )
                )
                await db_session.delete(row)
            await db_session.commit()
        return _response(payload_data())

    bounded_http(monkeypatch, handler)
    await process_receipt_read({}, str(ident))
    job = await db_session.get(ReceiptReadJob, ident, populate_existing=True)
    assert len(calls) == 1 and job.state == "superseded"
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadExtraction)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadReservation)) == 1


async def test_crash_after_reservation_is_unknown_no_http_on_restart(
    db_session, monkeypatch, tmp_path
):
    from app.documents.receipt_read_jobs import (
        ReceiptReadPrepared,
        claim_receipt_read,
        recover_receipt_reads,
        reserve_receipt_read_dispatch,
    )
    from app.documents.receipt_read_worker import process_receipt_read

    _, ident = await worker_ready(db_session, monkeypatch, tmp_path)
    now = datetime.now(UTC)
    config = get_receipt_read_config(settings)
    claim = await claim_receipt_read(db_session, ident, now=now, config=config)
    await db_session.commit()
    jpeg = valid_jpeg_bytes()
    prepared = ReceiptReadPrepared(jpeg, hashlib.sha256(jpeg).hexdigest(), 10000)
    assert await reserve_receipt_read_dispatch(db_session, claim, prepared, now=now, config=config)
    await db_session.commit()
    calls = []

    def handler(req):
        calls.append(req)
        return _response(payload_data())

    bounded_http(monkeypatch, handler)
    await process_receipt_read({}, str(ident))
    await recover_receipt_reads(db_session, now=now + timedelta(hours=1), limit=100)
    await db_session.commit()
    await process_receipt_read({}, str(ident))
    assert (
        calls == []
        and (await db_session.get(ReceiptReadJob, ident, populate_existing=True)).state == "unknown"
    )
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadReservation)) == 1


async def test_lease_expired_unmarked_retries_preparation_at_most_twice(
    db_session, monkeypatch, tmp_path
):
    from app.documents.receipt_read_jobs import claim_receipt_read, recover_receipt_reads

    _, ident = await worker_ready(db_session, monkeypatch, tmp_path)
    now = datetime.now(UTC)
    config = get_receipt_read_config(settings)
    assert await claim_receipt_read(db_session, ident, now=now, config=config)
    await db_session.commit()
    now += timedelta(seconds=181)
    await recover_receipt_reads(db_session, now=now, limit=100)
    await db_session.commit()
    assert await claim_receipt_read(
        db_session, ident, now=now + timedelta(seconds=31), config=config
    )
    await db_session.commit()
    now += timedelta(seconds=213)
    await recover_receipt_reads(db_session, now=now, limit=100)
    await db_session.commit()
    assert (
        await claim_receipt_read(db_session, ident, now=now + timedelta(hours=1), config=config)
        is None
    )
    job = await db_session.get(ReceiptReadJob, ident, populate_existing=True)
    assert job.state == "failed" and job.prepare_attempts == 2
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadReservation)) == 0


async def test_active_receipt_read_blocks_source_archive(db_session, monkeypatch, tmp_path):
    from app.documents.lifecycle import DocumentLifecycleError, set_document_archived
    from app.documents.receipt_read_worker import process_receipt_read

    r, ident = await worker_ready(db_session, monkeypatch, tmp_path)
    with pytest.raises(DocumentLifecycleError, match="document_processing_active"):
        await set_document_archived(db_session, r.owner, r.document_id, archived=True)
    await db_session.rollback()

    def handler(req):
        return _response(payload_data())

    bounded_http(monkeypatch, handler)
    await process_receipt_read({}, str(ident))
    await set_document_archived(db_session, r.owner, r.document_id, archived=True)
    await db_session.commit()


async def test_quota_utc_midnight_and_global_admission(db_session, monkeypatch, tmp_path):
    from app.documents.receipt_read_client import ReceiptReadProviderOutcome
    from app.documents.receipt_read_jobs import (
        ReceiptReadPrepared,
        claim_receipt_read,
        finish_receipt_read,
        reserve_receipt_read_dispatch,
    )

    r, ident = await worker_ready(db_session, monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "DOCUMENT_RECEIPT_ITEMS_DAILY_CALL_LIMIT_PER_USER", 1)
    monkeypatch.setattr(settings, "DOCUMENT_RECEIPT_ITEMS_DAILY_CALL_LIMIT_GLOBAL", 1)
    config = get_receipt_read_config(settings)
    jpeg = valid_jpeg_bytes()
    prepared = ReceiptReadPrepared(jpeg, hashlib.sha256(jpeg).hexdigest(), 10000)
    day = datetime(2026, 11, 4, 23, 59, tzinfo=UTC)
    ids = [ident]
    admissions = []
    for n, now in enumerate([day, day, day + timedelta(minutes=2)]):
        if n:
            async with client_for(db_session, r.owner) as client:
                response = await start(client, r, reread=str(ids[-1]))
                assert response.status_code == 200, response.text
                ident = uuid.UUID(response.json()["id"])
                ids.append(ident)
        claim = await claim_receipt_read(db_session, ident, now=now, config=config)
        await db_session.commit()
        assert claim
        reserved = await reserve_receipt_read_dispatch(
            db_session, claim, prepared, now=now, config=config
        )
        admissions.append(reserved)
        await db_session.commit()
        if reserved:
            await finish_receipt_read(
                db_session,
                claim,
                ReceiptReadProviderOutcome(error_code="timeout", uncertain=True),
                prepared,
                now=now,
                config=config,
            )
            await db_session.commit()
    assert admissions == [True, False, True]
    usages = (
        await db_session.scalars(
            select(ReceiptReadUsage).order_by(
                ReceiptReadUsage.usage_date, ReceiptReadUsage.scope_key
            )
        )
    ).all()
    assert len(usages) == 4 and all(u.reserved_calls == 1 for u in usages)
    assert {u.usage_date.isoformat() for u in usages} == {"2026-11-04", "2026-11-05"}
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadReservation)) == 2


async def test_late_finish_cannot_revive_terminal_unknown(db_session, monkeypatch, tmp_path):
    from app.documents.receipt_read_client import ReceiptReadProviderOutcome
    from app.documents.receipt_read_jobs import (
        ReceiptReadPrepared,
        claim_receipt_read,
        finish_receipt_read,
        recover_receipt_reads,
        reserve_receipt_read_dispatch,
    )
    from app.documents.receipt_read_payload import ReceiptReadPayload

    _, ident = await worker_ready(db_session, monkeypatch, tmp_path)
    now = datetime.now(UTC)
    config = get_receipt_read_config(settings)
    claim = await claim_receipt_read(db_session, ident, now=now, config=config)
    await db_session.commit()
    jpeg = valid_jpeg_bytes()
    prepared = ReceiptReadPrepared(jpeg, hashlib.sha256(jpeg).hexdigest(), 10000)
    assert await reserve_receipt_read_dispatch(db_session, claim, prepared, now=now, config=config)
    await db_session.commit()
    await recover_receipt_reads(db_session, now=now + timedelta(hours=1), limit=100)
    await db_session.commit()
    await finish_receipt_read(
        db_session,
        claim,
        ReceiptReadProviderOutcome(payload=ReceiptReadPayload.model_validate(payload_data())),
        prepared,
        now=now + timedelta(hours=1),
        config=config,
    )
    await db_session.commit()
    assert (await db_session.get(ReceiptReadJob, ident, populate_existing=True)).state == "unknown"
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadExtraction)) == 0


async def test_worker_registers_receipt_read_without_sdk_or_arq_retries():
    from app.worker import WorkerSettings

    functions = {
        getattr(f, "name", getattr(f, "__name__", "")): f for f in WorkerSettings.functions
    }
    assert "process_receipt_read" in functions
    assert functions["process_receipt_read"].max_tries == 1
    assert any(c.name.endswith("dispatch_receipt_reads") for c in WorkerSettings.cron_jobs)


async def test_finish_database_failure_cannot_repeat_http(db_session, monkeypatch, tmp_path):
    from app.documents import receipt_read_jobs as jobs
    from app.documents.receipt_read_worker import process_receipt_read

    _, ident = await worker_ready(db_session, monkeypatch, tmp_path)
    calls = []
    real_audit = jobs.log_event

    def handler(req):
        calls.append(req)
        return _response(payload_data())

    async def fail_success(db, *args, **kwargs):
        if "succeeded" in args:
            raise RuntimeError("synthetic audit transaction failure")
        return await real_audit(db, *args, **kwargs)

    bounded_http(monkeypatch, handler)
    monkeypatch.setattr(jobs, "log_event", fail_success)
    with pytest.raises(RuntimeError, match="synthetic audit"):
        await process_receipt_read({}, str(ident))
    await process_receipt_read({}, str(ident))
    assert len(calls) == 1
    assert (
        await db_session.get(ReceiptReadJob, ident, populate_existing=True)
    ).state == "dispatched"
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadExtraction)) == 0
    await jobs.recover_receipt_reads(
        db_session, now=datetime.now(UTC) + timedelta(hours=1), limit=100
    )
    await db_session.commit()
    assert (await db_session.get(ReceiptReadJob, ident, populate_existing=True)).state == "unknown"
