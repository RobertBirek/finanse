import uuid

import pytest
from sqlalchemy import func, select, update

from app.documents.receipt_read_models import (
    ReceiptReadJob,
    ReceiptReadReservation,
    ReceiptReadUsage,
)
from app.finance.models import FinanceCommandReceipt, FinancialDocument, Posting
from tests.test_finance.receipt_read_helpers import export, read_path, read_ready, start
from tests.test_finance.test_account_currency import client_for

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_preview_gets_create_no_jobs_usage_or_receipts(db_session, monkeypatch):
    r = await read_ready(db_session, monkeypatch)
    before = await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt))
    async with client_for(db_session, r.owner) as client:
        context = await client.get(read_path(r, "reads/context"))
        assert context.status_code == 200 and context.json()["enabled"], context.text
        assert context.json()["sources"][0]["document_id"] == str(r.document_id)
        p = await export(client, r)
        assert (
            "całego obrazu" in p["notice"] and "płatn" in p["notice"] and "nagłówka" in p["notice"]
        )
    for table in [ReceiptReadJob, ReceiptReadReservation, ReceiptReadUsage]:
        assert await db_session.scalar(select(func.count()).select_from(table)) == 0
    assert (
        await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == before
    )


async def test_two_start_keys_reuse_one_content_generation_and_old_receipt_replays(
    db_session, monkeypatch
):
    r = await read_ready(db_session, monkeypatch)
    before = await db_session.scalar(select(func.count()).select_from(Posting))
    async with client_for(db_session, r.owner) as client:
        p = await export(client, r)
        key = uuid.uuid4().hex
        first = await start(client, r, preview=p, key=key)
        assert first.status_code == 200, first.text
        second = await start(client, r, preview=p)
        assert second.status_code == 200, second.text
        assert first.json()["id"] == second.json()["id"] and first.json()["generation"] == 1
        job_id = uuid.UUID(first.json()["id"])
        await db_session.execute(
            update(ReceiptReadJob)
            .where(ReceiptReadJob.id == job_id)
            .values(state="failed", version=2, error_code="synthetic")
        )
        await db_session.commit()
        replay = await start(client, r, preview=p, key=key)
        assert replay.json() == first.json()
        canonical = await client.get(read_path(r, f"reads/{job_id}"))
        assert canonical.json()["state"] == "failed"
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadJob)) == 1
    assert await db_session.scalar(select(func.count()).select_from(Posting)) == before


async def test_two_rereads_of_one_prior_have_one_success_one_conflict(db_session, monkeypatch):
    r = await read_ready(db_session, monkeypatch)
    async with client_for(db_session, r.owner) as client:
        first = await start(client, r)
        assert first.status_code == 200, first.text
        job_id = first.json()["id"]
        c = await client.post(
            read_path(r, f"reads/{job_id}/cancel"),
            json={"expected_version": 1},
            headers={"Idempotency-Key": "cancel"},
        )
        assert c.status_code == 200 and c.json()["state"] == "cancelled", c.text
        p = await export(client, r, job_id)
        second = await start(client, r, preview=p)
        third = await start(client, r, preview=p)
        assert [second.status_code, third.status_code] == [200, 409]
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadJob)) == 2


async def test_cancel_unmarked_has_zero_reservations(db_session, monkeypatch):
    r = await read_ready(db_session, monkeypatch)
    async with client_for(db_session, r.owner) as client:
        first = await start(client, r)
        assert first.status_code == 200, first.text
        path = read_path(r, f"reads/{first.json()['id']}/cancel")
        response = await client.post(
            path, json={"expected_version": 1}, headers={"Idempotency-Key": "cancel"}
        )
        assert response.status_code == 200 and response.json()["state"] == "cancelled", (
            response.text
        )
        assert (
            await client.post(
                path, json={"expected_version": 1}, headers={"Idempotency-Key": "cancel"}
            )
        ).json() == response.json()
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadReservation)) == 0


@pytest.mark.parametrize("kind", ["header", "source", "policy", "env"])
async def test_stale_or_disabled_export_cannot_create_job(db_session, monkeypatch, kind):
    from app.config import settings
    from app.documents.receipt_read_policy import set_receipt_read_policy
    from app.finance.models import FinancialDocumentSource

    r = await read_ready(db_session, monkeypatch)
    async with client_for(db_session, r.owner) as client:
        p = await export(client, r)
        if kind == "header":
            await db_session.execute(
                update(FinancialDocument)
                .where(FinancialDocument.id == r.bill_id)
                .values(total_minor=9001, version=2)
            )
        if kind == "source":
            row = await db_session.scalar(
                select(FinancialDocumentSource).where(
                    FinancialDocumentSource.document_id == r.document_id
                )
            )
            await db_session.delete(row)
        if kind == "policy":
            await set_receipt_read_policy(
                db_session,
                enabled=False,
                expected_epoch=p["policy_epoch"],
                config=None,
                performed_by="synthetic",
            )
        if kind == "env":
            monkeypatch.setattr(settings, "DOCUMENT_RECEIPT_ITEMS_ENABLED", False)
        await db_session.commit()
        response = await start(client, r, preview=p)
        assert response.status_code in {404, 409, 422}, response.text
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadJob)) == 0


async def test_receipt_read_env_off_overrides_enabled_row_and_get_has_no_policy_insert(
    db_session, monkeypatch
):
    from app.documents.receipt_read_models import ReceiptReadPolicy

    r = await read_ready(db_session, monkeypatch, enable=False)
    async with client_for(db_session, r.owner) as client:
        context = await client.get(read_path(r, "reads/context"))
        assert context.status_code == 200 and not context.json()["enabled"], context.text
        assert await db_session.scalar(select(func.count()).select_from(ReceiptReadPolicy)) == 0
        assert (
            await client.post(
                read_path(r, "read-export-preview"), json={"document_id": str(r.document_id)}
            )
        ).status_code == 409
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadJob)) == 0


async def test_foreign_source_job_and_bill_never_leak(db_session, monkeypatch):
    r = await read_ready(db_session, monkeypatch)
    from tests.test_finance.receipt_helpers import ready

    other, bill, _, _, _, _, _ = await ready(db_session)
    foreign_bill = bill.id
    async with client_for(db_session, r.owner) as client:
        assert (
            await client.get(f"/api/finance/bills/{foreign_bill}/items/reads/context")
        ).status_code == 404
        assert (
            await client.post(
                read_path(r, "read-export-preview"), json={"document_id": str(uuid.uuid4())}
            )
        ).status_code == 404
    async with client_for(db_session, other) as client:
        assert (await client.get(read_path(r, "reads/context"))).status_code == 404


async def test_job_history_and_sources_page_without_missing_equal_timestamps(
    db_session, monkeypatch
):
    from app.config import settings
    from app.documents.models import Document
    from app.finance.models import FinancialDocumentSource

    r = await read_ready(db_session, monkeypatch)
    for n in range(3):
        d = Document(
            user_id=r.owner,
            filename=f"synthetic{n}.pdf",
            original_name="synthetic.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            storage_path="synthetic.pdf",
            sha256_hash=str(n) * 64,
            status="done",
        )
        db_session.add(d)
        await db_session.flush()
        db_session.add(
            FinancialDocumentSource(
                user_id=r.owner, financial_document_id=r.bill_id, document_id=d.id
            )
        )
    await db_session.commit()
    monkeypatch.setattr(settings, "DOCUMENT_RECEIPT_ITEMS_PAGE_SIZE", 1)
    async with client_for(db_session, r.owner) as client:
        ids = []
        cursor = None
        for _ in range(5):
            response = await client.get(
                read_path(r, "reads/context"), params={"source_cursor": cursor} if cursor else {}
            )
            assert response.status_code == 200, response.text
            page = response.json()
            ids.extend(s["document_id"] for s in page["sources"])
            cursor = page["next_source_cursor"]
            for source in page["sources"]:
                if source["mime_type"] == "application/pdf":
                    assert not source["allowed"]
            if not cursor:
                break
        assert len(ids) == len(set(ids)) == 4
        job_id = None
        for n in range(3):
            p = await export(client, r, job_id if n else None)
            result = await start(client, r, preview=p)
            assert result.status_code == 200, result.text
            job_id = result.json()["id"]
            response = await client.post(
                read_path(r, f"reads/{job_id}/cancel"),
                json={"expected_version": 1},
                headers={"Idempotency-Key": uuid.uuid4().hex},
            )
            assert response.status_code == 200, response.text
        ids = []
        cursor = None
        for _ in range(4):
            page = (
                await client.get(read_path(r, "reads"), params={"cursor": cursor} if cursor else {})
            ).json()
            ids.extend(j["id"] for j in page["items"])
            cursor = page["next_cursor"]
            if not cursor:
                break
        assert len(ids) == len(set(ids)) == 3
        for suffix in ["reads?cursor=!!!!", "reads/context?source_cursor=!!!!"]:
            assert (await client.get(read_path(r, suffix))).status_code == 422


async def test_read_start_same_key_different_body_conflicts(db_session, monkeypatch):
    r = await read_ready(db_session, monkeypatch)
    async with client_for(db_session, r.owner) as client:
        p = await export(client, r)
        result = await start(client, r, preview=p, key="same-intent")
        assert result.status_code == 200, result.text
        changed = {**p, "export_snapshot": "f" * 64}
        result = await start(client, r, preview=changed, key="same-intent")
        assert result.status_code == 409, result.text
