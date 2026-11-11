"""Real private synthetic PDF -> durable worker -> HTTP activation -> fresh sessions.

Breaks caught: successful activation missing from batch read, paid IDs rewritten on
renumbering, changed payment snapshot accepted, duplicate source/version creation.
No fake parsed rows, parser mocks, customer PDFs, or production connections.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.documents import service as documents
from app.finance import loans
from app.finance.imports import worker
from app.finance.imports.models import ImportRow, ImportSource
from app.finance.loan_schedule_models import LoanScheduleRevision
from app.finance.loan_schemas import LoanInstallmentCreate
from app.finance.models import FinanceCommandReceipt, LoanInstallment, LoanPaymentLink
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bank_imports.factories import text_pdf_bytes
from tests.test_finance.test_loan_schedule_import.factories import (
    financial_history_snapshot,
    legacy_loan,
    payment_transfer,
)
from tests.test_finance.test_loan_schedule_import.test_parser import HEADER, ROW1, ROW2, ROW3

pytestmark = pytest.mark.integration
ROOT = "/api/finance/imports"


async def stage_schedule(db, sessions, owner_id, monkeypatch, text):
    content = text_pdf_bytes(text)
    async with client_for(db, owner_id) as client:
        response = await client.post(
            ROOT, json={"kind": "loan_schedule"}, headers={"Idempotency-Key": uuid.uuid4().hex}
        )
        assert response.status_code == 201, response.text
        batch_id = response.json()["id"]
        uploaded = await client.post(
            f"{ROOT}/{batch_id}/sources",
            files={"file": ("synthetic-schedule.pdf", content, "application/pdf")},
            headers={"Idempotency-Key": uuid.uuid4().hex},
        )
        assert uploaded.status_code == 201, uploaded.text
        source = uploaded.json()["source"]
        prepared = await client.post(
            f"{ROOT}/{batch_id}/sources/{source['id']}/prepare",
            headers={"Idempotency-Key": uuid.uuid4().hex},
        )
        assert prepared.status_code == 200, prepared.text
    await db.commit()
    monkeypatch.setattr(worker, "async_session_factory", sessions)
    await worker.process_import_job({}, prepared.json()["id"])
    return batch_id, source, content


async def preview_http(client, batch_id, source_id, loan_id):
    loaded = await client.get(f"{ROOT}/{batch_id}")
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["sources"][0]["processing_state"] == "ready"
    response = await client.post(
        f"{ROOT}/{batch_id}/schedule-preview",
        json={
            "expected_version": loaded.json()["version"],
            "source_id": source_id,
            "target": {"loan_id": str(loan_id)},
            "acknowledgements": [f"schedule_target:{source_id}"],
        },
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def activate_http(client, batch_id, preview, key):
    return await client.post(
        f"{ROOT}/{batch_id}/activate-schedule",
        json={"preview_id": preview["id"], "request_hash": preview["request_hash"]},
        headers={"Idempotency-Key": key},
    )


async def seed(db, owner_id):
    loan, item, _receipt = await legacy_loan(db, owner_id)
    item.due_date = date(2026, 12, 15)
    item.principal_pln = 100000
    item.interest_pln = 2000
    await db.flush()
    transfer = await payment_transfer(db, owner_id, loan)
    await loans.link_loan_payment(db, owner_id, loan.id, item.id, transfer.id)
    return loan.id, item.id, transfer.id


async def test_worker_to_activation_fresh_read_receipt_original_and_duplicate(
    db_session, test_database, owner, other_owner, tmp_path, monkeypatch
):
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    owner_id = owner.id
    foreign_id = other_owner.id
    loan_id, item_id, tx_id = await seed(db_session, owner_id)
    before = await financial_history_snapshot(db_session)
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    batch_id, source, content = await stage_schedule(
        db_session, sessions, owner_id, monkeypatch, HEADER + ROW1 + ROW2 + ROW3 + "Strona 1 z 1"
    )
    async with sessions() as db:
        async with client_for(db, owner_id) as client:
            preview = await preview_http(client, batch_id, source["id"], loan_id)
            assert preview["diff"]["reused_ids"] == [str(item_id)]
            assert len(preview["diff"]["new_rows"]) == 2 and not preview["diff"]["conflicts"]
            assert await financial_history_snapshot(db) == before
            response = await activate_http(client, batch_id, preview, "accept-schedule")
            assert response.status_code == 200, response.text
            receipt = response.json()
            assert not receipt["ledger_changed"] and receipt["reused_ids"] == [str(item_id)]
            assert (
                await activate_http(client, batch_id, preview, "accept-schedule")
            ).json() == receipt
        await db.commit()
    async with sessions() as db:
        async with client_for(db, owner_id) as client:
            assert (
                await client.get(f"{ROOT}/{batch_id}/commands/accept-schedule")
            ).json() == receipt
            detail = (await client.get(f"/api/finance/loans/{loan_id}")).json()
            assert detail["active_schedule_revision_id"] == receipt["revision_id"]
            assert len(detail["installments"]) == 3
            paid = next(i for i in detail["installments"] if i["id"] == str(item_id))
            assert paid["payment_status"] == "partial" and paid["paid_pln"] == 100
            assert paid["payments"][0]["transaction_id"] == str(tx_id)
            assert paid["number"] == 1 and paid["bank_number"] == 1
            listing = (await client.get("/api/finance/loans")).json()
            assert listing[0]["total_planned_pln"] == 303500 and listing[0]["paid_pln"] == 100
            candidates = await client.get(
                f"/api/finance/loans/{loan_id}/installments/{item_id}/payment-candidates"
            )
            assert candidates.status_code == 200, candidates.text
            history = (await client.get(f"/api/finance/loans/{loan_id}/schedule-revisions")).json()
            assert len(history) == 2
            active = next(v for v in history if v["state"] == "active")
            assert active["document_id"] == source["document_id"]
            original = await client.get(f"/api/documents/{source['document_id']}/original")
            assert original.status_code == 200 and original.content == content
            duplicate = await client.post(
                f"{ROOT}/{batch_id}/sources",
                files={"file": ("same.pdf", content, "application/pdf")},
                headers={"Idempotency-Key": "same-bytes"},
            )
            assert duplicate.status_code == 201 and duplicate.json()["is_duplicate"]
            assert duplicate.json()["existing_batch_id"] == batch_id
            loaded = (await client.get(f"{ROOT}/{batch_id}")).json()
            assert loaded["commit_state"] == "committed" and loaded["unresolved_count"] == 0
        async with client_for(db, foreign_id) as client:
            assert (
                await client.get(f"/api/documents/{source['document_id']}/original")
            ).status_code == 404
        from app.documents.lifecycle import DocumentLifecycleError, set_document_archived

        document_id = uuid.UUID(source["document_id"])
        with pytest.raises(DocumentLifecycleError) as caught:
            await set_document_archived(db, owner_id, document_id, archived=True)
        assert caught.value.code == "document_import_source"
        with pytest.raises(DocumentLifecycleError) as caught:
            await documents.delete_document(db, owner_id, document_id)
        assert caught.value.code == "document_import_source"
        assert await financial_history_snapshot(db) == before
        assert await db.scalar(select(func.count()).select_from(LoanScheduleRevision)) == 2
        assert await db.scalar(select(func.count()).select_from(ImportSource)) == 1
        assert await db.scalar(select(func.count()).select_from(ImportRow)) == 3


async def test_shorter_renumbered_worker_plan_preserves_paid_history_and_excludes_old_tail(
    db_session, test_database, owner, tmp_path, monkeypatch
):
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    owner_id = owner.id
    loan_id, item_id, _tx_id = await seed(db_session, owner_id)
    old_tail = await loans.create_loan_installment(
        db_session,
        owner_id,
        loan_id,
        LoanInstallmentCreate(
            number=90, due_date="2028-01-15", principal_pln=1000, interest_pln=0, fees_pln=0
        ),
    )
    old_tail_id = old_tail.id
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    first_batch, first_source, _ = await stage_schedule(
        db_session, sessions, owner_id, monkeypatch, HEADER + ROW1 + ROW2 + ROW3 + "Strona 1 z 1"
    )
    async with sessions() as db:
        async with client_for(db, owner_id) as client:
            preview = await preview_http(client, first_batch, first_source["id"], loan_id)
            response = await activate_http(client, first_batch, preview, "first-plan")
            assert response.status_code == 200, response.text
        await db.commit()
    # Bank resets remaining rows to 1..2; the linked first installment is now history.
    text = (
        HEADER.replace("2026-11-01", "2026-12-20")
        + ROW2.replace("2 2027", "1 2027")
        + ROW3.replace("3 2027", "2 2027")
        + "Strona 1 z 1"
    )
    batch_id, source, _ = await stage_schedule(db_session, sessions, owner_id, monkeypatch, text)
    async with sessions() as db:
        before = await financial_history_snapshot(db)
        raw_before = (
            await db.execute(select(LoanInstallment.__table__).where(LoanInstallment.id == item_id))
        ).one()
        async with client_for(db, owner_id) as client:
            preview = await preview_http(client, batch_id, source["id"], loan_id)
            assert (
                not preview["diff"]["conflicts"]
                and str(item_id) in preview["diff"]["retained_history_ids"]
            )
            response = await activate_http(client, batch_id, preview, "remaining-plan")
            assert response.status_code == 200, response.text
            assert not response.json()["new_ids"] and len(response.json()["reused_ids"]) == 2
        await db.commit()
    async with sessions() as db:
        assert (
            await db.execute(select(LoanInstallment.__table__).where(LoanInstallment.id == item_id))
        ).one() == raw_before
        assert await financial_history_snapshot(db) == before
        detail = await loans.get_loan(db, owner_id, loan_id)
        assert (
            detail is not None
            and len(detail.installments) == 3
            and detail.total_planned_pln == 303500
        )
        assert old_tail_id not in {i.id for i in detail.installments}
        assert await db.get(LoanInstallment, old_tail_id) is not None
        assert await db.scalar(select(LoanPaymentLink.installment_id)) == item_id


async def test_payment_between_worker_preview_and_activation_returns_409_without_plan_or_receipt(
    db_session, test_database, owner, tmp_path, monkeypatch
):
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    owner_id = owner.id
    loan_id, item_id, _ = await seed(db_session, owner_id)
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    batch_id, source, _ = await stage_schedule(
        db_session, sessions, owner_id, monkeypatch, HEADER + ROW1 + ROW2 + ROW3 + "Strona 1 z 1"
    )
    async with sessions() as db:
        async with client_for(db, owner_id) as client:
            preview = await preview_http(client, batch_id, source["id"], loan_id)
        await db.commit()
    async with sessions() as db:
        from app.finance.models import LoanAgreement

        loan = await db.get(LoanAgreement, loan_id)
        transfer = await payment_transfer(db, owner_id, loan)
        await loans.link_loan_payment(db, owner_id, loan_id, item_id, transfer.id)
        await db.commit()
    async with sessions() as db:
        before = await financial_history_snapshot(db)
        async with client_for(db, owner_id) as client:
            rejected = await activate_http(client, batch_id, preview, "stale-worker-plan")
            assert rejected.status_code == 409, rejected.text
        assert await financial_history_snapshot(db) == before
        assert await db.scalar(select(func.count()).select_from(LoanScheduleRevision)) == 0
        assert (
            await db.scalar(
                select(func.count())
                .select_from(FinanceCommandReceipt)
                .where(FinanceCommandReceipt.key == "stale-worker-plan")
            )
            == 0
        )
