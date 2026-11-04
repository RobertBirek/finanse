import uuid

import pytest
from sqlalchemy import func, select

from app.finance.categorization_context import columns
from app.finance.models import (
    DocumentPaymentAllocation,
    FinanceCommandReceipt,
    FinancialDocument,
    FinancialTransaction,
    TransactionCategorizationState,
)
from tests.test_finance.receipt_helpers import (
    ROOT,
    approve_items,
    mutate,
    payload,
    ready,
    save,
    store_for,
)
from tests.test_finance.test_account_currency import client_for

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def payment_ready(db, *, allocate=True):
    owner, bill, txn, account, marker, food, home = await ready(db)
    async with client_for(db, owner) as client:
        store = await store_for(client)
        approved = await approve_items(
            client, bill.id, await save(client, bill, payload(food, home, store))
        )
    if allocate:
        db.add(
            DocumentPaymentAllocation(
                user_id=owner,
                financial_document_id=bill.id,
                posting_id=next(p.id for p in txn.postings if p.account_id),
                amount_minor=9000,
            )
        )
        bill.version += 1
        await db.commit()
        await db.refresh(bill)
    return owner, bill, txn, account, marker, food, home, approved, store


async def preview(client, bill_id, approved):
    r = await client.post(
        f"{ROOT}/bills/{bill_id}/items/payment-preview",
        json={
            "expected_state_version": approved["state_version"],
            "approved_revision_id": approved["approved"]["id"],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


async def apply(client, bill_id, p, key=None, **extra):
    return await mutate(
        client,
        f"/bills/{bill_id}/items/payment-apply",
        {
            "expected_state_version": p["expected_state_version"],
            "approved_revision_id": p["approved_revision_id"],
            "expected_preview_snapshot": p["preview_snapshot"],
            "confirmed": True,
            **extra,
        },
        key=key,
    )


async def test_unallocated_products_approve_without_creating_payment(db_session):
    owner, bill, _, _, _, _, _, approved, _ = await payment_ready(db_session, allocate=False)
    before = await db_session.scalar(select(func.count()).select_from(FinancialTransaction))
    async with client_for(db_session, owner) as client:
        r = await client.get(f"{ROOT}/bills/{bill.id}/items/payment")
        assert r.status_code == 200 and not r.json()["allowed"], r.text
        r = await client.post(
            f"{ROOT}/bills/{bill.id}/items/payment-preview",
            json={"expected_state_version": 2, "approved_revision_id": approved["approved"]["id"]},
        )
        assert r.status_code == 409, r.text
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == before


async def test_full_payment_apply_preserves_account_and_allocations_exactly(db_session):
    from app.finance.rule_models import TransactionCategorizationOrigin as Origin

    owner, bill, txn, _, _, food, home, approved, _ = await payment_ready(db_session)
    bill_id, txn_id, food_id, home_id = bill.id, txn.id, food.id, home.id
    before_bill = columns(bill)
    before_account = columns(next(p for p in txn.postings if p.account_id))
    before_alloc = [
        columns(a) for a in (await db_session.scalars(select(DocumentPaymentAllocation))).all()
    ]
    async with client_for(db_session, owner) as client:
        p = await preview(client, bill_id, approved)
        assert {x["category_id"]: x["amount_minor"] for x in p["after_parts"]} == {
            str(food_id): 7200,
            str(home_id): 1800,
        }
        key = uuid.uuid4().hex
        result = await apply(client, bill_id, p, key)
        assert result.status_code == 200, result.text
        assert result.json()["context"]["assignment_origin"]["origin"] == "manual"
        assert (await apply(client, bill_id, p, key)).json() == result.json()
        status = (await client.get(f"{ROOT}/bills/{bill_id}/items/payment")).json()[
            "last_application"
        ]
        assert status and not status["ledger_changed"] and not status["items_changed"]
    await db_session.refresh(txn, ["postings"])
    await db_session.refresh(bill)
    assert columns(bill) == before_bill
    assert columns(next(p for p in txn.postings if p.account_id)) == before_account
    assert [
        columns(a) for a in (await db_session.scalars(select(DocumentPaymentAllocation))).all()
    ] == before_alloc
    assert sum(p.base_amount_pln * (1 if p.direction == "debit" else -1) for p in txn.postings) == 0
    assert (
        len(txn.postings) == 3
        and await db_session.scalar(select(Origin.origin).where(Origin.transaction_id == txn_id))
        == "manual"
    )


@pytest.mark.parametrize(
    "kind",
    [
        "partial",
        "multiple",
        "foreign_allocation",
        "actual",
        "pending",
        "fx",
        "new_draft",
        "bill_total",
        "store",
        "archive_category",
    ],
)
async def test_protected_or_changed_sources_never_apply(db_session, kind):
    owner, bill, txn, _, _, food, home, approved, store = await payment_ready(db_session)
    bill_id = bill.id
    async with client_for(db_session, owner) as client:
        p = await preview(client, bill_id, approved)
        if kind == "partial":
            row = await db_session.scalar(select(DocumentPaymentAllocation))
            row.amount_minor = 8000
        if kind in {"multiple", "foreign_allocation"}:
            other = FinancialDocument(user_id=owner)
            db_session.add(other)
            await db_session.flush()
            db_session.add(
                DocumentPaymentAllocation(
                    user_id=uuid.uuid4() if kind == "foreign_allocation" else owner,
                    financial_document_id=other.id,
                    posting_id=next(p.id for p in txn.postings if p.account_id),
                    amount_minor=1,
                )
            )
        if kind == "actual":
            txn.source = "actual"
        if kind == "pending":
            txn.is_pending = True
        if kind == "fx":
            next(p for p in txn.postings if p.account_id).source_currency = "EUR"
        if kind == "bill_total":
            bill.total_minor = 9001
            bill.version += 1
        if kind == "archive_category":
            food.is_active = False
        if kind == "store":
            await mutate(
                client,
                f"/receipt-stores/{store['id']}",
                {"expected_version": 1, "active": False},
                method="patch",
            )
        if kind == "new_draft":
            await save(client, bill, payload(food, home, store), 2)
        await db_session.commit()
        result = await apply(client, bill_id, p)
        assert result.status_code == 409, result.text
    assert (
        await db_session.scalar(select(func.count()).select_from(TransactionCategorizationState))
        == 0
    )


async def test_apply_requires_true_and_rejects_amount_parts_origin_override(db_session):
    owner, bill, _, _, _, _, _, approved, _ = await payment_ready(db_session)
    bill_id = bill.id
    async with client_for(db_session, owner) as client:
        p = await preview(client, bill_id, approved)
        for extra in [
            {"confirmed": 1},
            {"confirmed": False},
            {"parts": []},
            {"origin": "approved_llm"},
            {"amount_minor": 1},
        ]:
            assert (await apply(client, bill_id, p, **extra)).status_code == 422


async def test_audit_failure_rolls_back_payment_pointer_and_receipt(db_session, monkeypatch):
    from app.finance import receipt_commands
    from app.finance.receipt_models import ReceiptItemState
    from app.finance.receipt_payment import apply_receipt_payment
    from app.finance.receipt_schemas import ReceiptPaymentApply

    owner, bill, txn, _, _, _, _, approved, _ = await payment_ready(db_session)
    bill_id, txn_id = bill.id, txn.id
    async with client_for(db_session, owner) as client:
        p = await preview(client, bill_id, approved)
    await db_session.commit()

    async def fail(*args, **kwargs):
        raise RuntimeError("Synthetic audit failure")

    monkeypatch.setattr(receipt_commands, "log_event", fail)
    with pytest.raises(RuntimeError):
        await apply_receipt_payment(
            db_session,
            owner,
            bill_id,
            ReceiptPaymentApply(
                expected_state_version=2,
                approved_revision_id=p["approved_revision_id"],
                expected_preview_snapshot=p["preview_snapshot"],
                confirmed=True,
            ),
            idempotency_key="audit-rollback",
        )
    await db_session.rollback()
    state = await db_session.scalar(
        select(ReceiptItemState).where(ReceiptItemState.bill_id == bill_id)
    )
    assert state.version == 2 and state.last_apply_receipt_id is None
    assert (
        await db_session.scalar(
            select(TransactionCategorizationState.id).where(
                TransactionCategorizationState.transaction_id == txn_id
            )
        )
        is None
    )
    assert (
        await db_session.scalar(
            select(FinanceCommandReceipt.id).where(FinanceCommandReceipt.key == "audit-rollback")
        )
        is None
    )


async def test_same_parts_are_still_manual_evidence_and_later_edit_keeps_historical_replay(
    db_session,
):
    from app.finance.categorization import apply_categorization
    from app.finance.categorization_schemas import CategorizationApply
    from app.finance.receipt_models import ReceiptItemState
    from tests.test_finance.test_categorization import preview as manual_preview

    owner, bill, txn, _, marker, _food, _, approved, _store = await payment_ready(db_session)
    bill_id, txn_id = bill.id, txn.id
    async with client_for(db_session, owner) as client:
        first = await preview(client, bill_id, approved)
        result = await apply(client, bill_id, first, "original")
        assert result.status_code == 200, result.text
        current = (await client.get(f"{ROOT}/bills/{bill_id}/items")).json()
        p = await preview(client, bill_id, current)
        assert p["before_parts"] == p["after_parts"]
        second = await apply(client, bill_id, p, "sameparts")
        assert second.status_code == 200, second.text
        assert second.json()["receipt_id"] != result.json()["receipt_id"]
        manual = await manual_preview(
            client, txn, [{"category_id": str(marker.id), "amount_minor": 9000}]
        )
        await apply_categorization(
            db_session,
            owner,
            txn_id,
            CategorizationApply(
                expected_version=manual["expected_version"],
                expected_preview_snapshot=manual["preview_snapshot"],
                parts=manual["after_parts"],
                confirmed=True,
            ),
            idempotency_key="manual-later",
        )
        await db_session.commit()
        assert (await client.get(f"{ROOT}/bills/{bill_id}/items/payment")).json()[
            "last_application"
        ]["ledger_changed"]
        again = await apply(client, bill_id, first, "original")
        assert again.json() == result.json()
    assert (
        await db_session.scalar(
            select(ReceiptItemState.version).where(ReceiptItemState.bill_id == bill_id)
        )
        == 4
    )


@pytest.mark.parametrize("change", ["supplier", "total", "store", "category", "version_only"])
async def test_application_status_marks_semantically_stale_receipt_evidence(db_session, change):
    from app.finance.receipt_models import ReceiptStore

    owner, bill, _, _, _, food, _, approved, store = await payment_ready(db_session)
    bill_id = bill.id
    async with client_for(db_session, owner) as client:
        p = await preview(client, bill_id, approved)
        result = await apply(client, bill_id, p)
        assert result.status_code == 200, result.text
        if change == "supplier":
            bill.supplier_name = "Poprawiony sprzedawca"
        if change == "total":
            bill.total_minor = 9001
        if change == "store":
            row = await db_session.get(ReceiptStore, uuid.UUID(store["id"]))
            row.version += 1
        if change == "category":
            food.name = "Nowa nazwa ścieżki"
        bill.version += 1
        await db_session.commit()
        status = (await client.get(f"{ROOT}/bills/{bill_id}/items/payment")).json()
        assert status["last_application"]["items_changed"] == (change != "version_only"), status
        assert not status["last_application"]["ledger_changed"]
        assert status["allowed"] == (change == "version_only")
