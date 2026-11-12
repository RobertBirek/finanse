"""Declarations must remove obligations, never manufacture bank evidence."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.audit.models import AuditEvent
from app.finance.bill_coverage import decide_coverage
from app.finance.bill_forecast import project_bill_cashflows
from app.finance.bill_payments import allocate_payment, unlink_payment
from app.finance.bills import get_bill
from app.finance.bills_schemas import AllocationCreate, CoverageDecision, MutationContext
from app.finance.models import (
    Account,
    DocumentPaymentAllocation,
    FinanceCommandReceipt,
    FinancialTransaction,
    Posting,
    RecurringOccurrenceCoverage,
)
from app.finance.schemas import ScheduledFinanceItemCreate
from app.finance.service import create_scheduled_item
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bill_payments import create_owner, expense, setup_bill

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def command(version: int = 2, declaration: str = "declared_paid") -> dict[str, object]:
    return {
        "expected_version": version,
        "declaration": declaration,
        "confirm_forecast_effect": True,
    }


async def snapshot(db) -> list[list[tuple]]:
    return [
        list((await db.execute(select(model.__table__).order_by(model.id))).tuples())
        for model in (Account, FinancialTransaction, Posting, DocumentPaymentAllocation)
    ]


async def test_declaration_never_creates_ledger_or_allocation(db_session) -> None:
    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    await expense(db_session, owner, 1234)
    bill_id = bill.id
    before = await snapshot(db_session)
    async with client_for(db_session, owner) as client:
        response = await client.post(
            f"/api/finance/bills/{bill_id}/payment-declaration",
            json=command(),
            headers={"Idempotency-Key": "declare"},
        )
    assert response.status_code == 200, response.text
    result = response.json()
    assert (
        result["declaration"],
        result["paid_minor"],
        result["remaining_minor"],
        result["reconciliation"],
        result["version"],
    ) == ("declared_paid", 0, 10000, "none", 3)
    assert result["allocations"] == []
    assert await snapshot(db_session) == before
    event = await db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(bill_id),
            AuditEvent.action == "payment_declaration",
        )
    )
    assert event.user_id == owner and event.performed_by == "human"
    assert event.old_state == {"declaration": "unknown", "version": 2}
    assert event.new_state == {
        "declaration": "declared_paid",
        "version": 3,
        "remaining_minor": 10000,
        "currency": "PLN",
        "without_transaction": True,
    }


async def test_idempotency_and_owner_version_guards(db_session) -> None:
    owner, other = await create_owner(db_session), await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    bill_id = bill.id
    await db_session.commit()
    url = f"/api/finance/bills/{bill_id}/payment-declaration"
    async with client_for(db_session, owner) as client:
        first = await client.post(url, json=command(), headers={"Idempotency-Key": "same"})
        replay = await client.post(url, json=command(), headers={"Idempotency-Key": "same"})
        assert first.status_code == 200, first.text
        assert replay.json() == first.json()
        reused = await client.post(
            url, json=command(3, "payable"), headers={"Idempotency-Key": "same"}
        )
        assert reused.status_code == 409
        stale = await client.post(
            url, json=command(2, "payable"), headers={"Idempotency-Key": "stale"}
        )
        assert stale.status_code == 409
        noop = await client.post(url, json=command(3), headers={"Idempotency-Key": "noop"})
        assert noop.status_code == 200 and noop.json()["version"] == 3
    async with client_for(db_session, other) as client:
        hidden = await client.post(url, json=command(3), headers={"Idempotency-Key": "hidden"})
        missing = await client.post(
            f"/api/finance/bills/{uuid.uuid4()}/payment-declaration",
            json=command(),
            headers={"Idempotency-Key": "missing"},
        )
        assert hidden.status_code == missing.status_code == 404
    events = list(
        await db_session.scalars(
            select(AuditEvent).where(AuditEvent.action == "payment_declaration")
        )
    )
    assert len(events) == 1
    receipts = list(
        await db_session.scalars(
            select(FinanceCommandReceipt).where(
                FinanceCommandReceipt.action == "set_bill_payment_declaration"
            )
        )
    )
    assert len(receipts) == 2  # successful command and a separately requested noop only


@pytest.mark.parametrize("state", ["draft", "rejected", "archived", "cancelled", "full"])
async def test_lifecycle_and_request_guards(db_session, state: str) -> None:
    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    if state in {"draft", "rejected"}:
        bill.review = state
    elif state != "full":
        bill.lifecycle = state
    version = 2
    if state == "full":
        posting, _, _ = await expense(db_session, owner, 10000)
        await allocate_payment(
            db_session,
            owner,
            bill.id,
            AllocationCreate(version=2, posting_id=posting, amount_minor=10000),
            context=MutationContext(idempotency_key="full"),
        )
        version = 3
    bill_id = bill.id
    await db_session.commit()
    async with client_for(db_session, owner) as client:
        rejected = await client.post(
            f"/api/finance/bills/{bill_id}/payment-declaration",
            json=command(version),
            headers={"Idempotency-Key": "invalid"},
        )
    assert rejected.status_code == 422, rejected.text


@pytest.mark.parametrize(
    "patch",
    [
        {"amount_minor": 5000},
        {"confirm_forecast_effect": False},
        {"expected_version": True},
        {"expected_version": "2"},
        {"declaration": "unknown"},
    ],
)
async def test_request_rejects_partial_or_unconfirmed_declarations(db_session, patch: dict) -> None:
    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    bill_id = bill.id
    await db_session.commit()
    async with client_for(db_session, owner) as client:
        response = await client.post(
            f"/api/finance/bills/{bill_id}/payment-declaration",
            json={**command(), **patch},
            headers={"Idempotency-Key": "bad-input"},
        )
    assert response.status_code == 422
    unchanged = await get_bill(db_session, owner, bill_id)
    assert unchanged.version == 2 and unchanged.declaration == "unknown"


@pytest.mark.parametrize("currency", ["PLN", "EUR", "USD"])
async def test_declaration_without_payment_account_all_currencies(
    db_session, currency: str
) -> None:
    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner, currency=currency)
    bill_id = bill.id
    before = await snapshot(db_session)
    async with client_for(db_session, owner) as client:
        response = await client.post(
            f"/api/finance/bills/{bill_id}/payment-declaration",
            json=command(),
            headers={"Idempotency-Key": "no-account"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["payment_account_id"] is None
        if currency != "PLN":
            candidates = await client.get(f"/api/finance/bills/{bill_id}/candidates")
            assert candidates.status_code == 200
            assert candidates.json()["items"] == []
            allocation = await client.post(
                f"/api/finance/bills/{bill_id}/allocations",
                json={"version": 3, "posting_id": str(uuid.uuid4()), "amount_minor": 10000},
                headers={"Idempotency-Key": "foreign-allocation"},
            )
            assert allocation.status_code == 422
    assert await snapshot(db_session) == before
    projection = await project_bill_cashflows(
        db_session, owner, today=date(2026, 11, 12), horizon_end=date(2026, 12, 12)
    )
    assert projection.entries == [] and projection.exclusions == []
    assert projection.day_changes_pln == {}


async def test_real_allocations_replace_declared_remainder_without_double_count(db_session) -> None:
    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    bill_id = bill.id
    first, _, _ = await expense(db_session, owner, 4000)
    second, _, _ = await expense(db_session, owner, 6000)
    async with client_for(db_session, owner) as client:
        response = await client.post(
            f"/api/finance/bills/{bill_id}/payment-declaration",
            json=command(),
            headers={"Idempotency-Key": "declare"},
        )
    assert response.status_code == 200
    partial = await allocate_payment(
        db_session,
        owner,
        bill_id,
        AllocationCreate(version=3, posting_id=first, amount_minor=4000),
        context=MutationContext(idempotency_key="partial"),
    )
    assert (
        partial.paid_minor,
        partial.remaining_minor,
        partial.declaration,
        partial.reconciliation,
    ) == (4000, 6000, "declared_paid", "partial")
    full = await allocate_payment(
        db_session,
        owner,
        bill_id,
        AllocationCreate(version=4, posting_id=second, amount_minor=6000),
        context=MutationContext(idempotency_key="full"),
    )
    assert (full.paid_minor, full.remaining_minor, full.reconciliation) == (10000, 0, "full")
    unlinked = await unlink_payment(
        db_session,
        owner,
        bill_id,
        full.allocations[-1].id,
        5,
        context=MutationContext(idempotency_key="unlink"),
    )
    assert unlinked.declaration == "declared_paid" and unlinked.reconciliation == "partial"


async def test_undo_and_coverage_preserve_single_remaining_cashflow(db_session) -> None:
    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    posting, account, category = await expense(db_session, owner, 4000)
    bill.due_date = date(2026, 11, 12)
    bill.payment_account_id, bill.category_id, bill.declaration = account.id, category.id, "payable"
    rule = await create_scheduled_item(
        db_session,
        owner,
        ScheduledFinanceItemCreate(
            name="Estimate",
            type="expense",
            account_id=account.id,
            category_id=category.id,
            currency="PLN",
            due_day=12,
            amount_method="fixed",
            fixed_amount_pln=12000,
        ),
    )
    bill_id, rule_id = bill.id, rule.id
    await decide_coverage(
        db_session,
        owner,
        bill_id,
        CoverageDecision(
            version=2,
            choice="replace",
            scheduled_item_id=rule_id,
            occurrence_date=date(2026, 11, 12),
        ),
        context=MutationContext(idempotency_key="cover"),
    )
    await allocate_payment(
        db_session,
        owner,
        bill_id,
        AllocationCreate(version=3, posting_id=posting, amount_minor=4000),
        context=MutationContext(idempotency_key="partial"),
    )
    async with client_for(db_session, owner) as client:
        marked = await client.post(
            f"/api/finance/bills/{bill_id}/payment-declaration",
            json=command(4),
            headers={"Idempotency-Key": "mark"},
        )
        assert marked.status_code == 200, marked.text
        projection = await project_bill_cashflows(
            db_session, owner, today=date(2026, 11, 12), horizon_end=date(2026, 12, 12)
        )
        assert projection.entries == [] and projection.exclusions == []
        assert projection.covered_occurrences == {(rule_id, date(2026, 11, 12))}
        undone = await client.post(
            f"/api/finance/bills/{bill_id}/payment-declaration",
            json=command(5, "payable"),
            headers={"Idempotency-Key": "undo"},
        )
        assert undone.status_code == 200, undone.text
    projection = await project_bill_cashflows(
        db_session, owner, today=date(2026, 11, 12), horizon_end=date(2026, 12, 12)
    )
    assert len(projection.entries) == 1 and projection.entries[0].amount_minor == 6000
    assert projection.day_changes_pln == {date(2026, 11, 12): -6000}
    assert projection.covered_occurrences == {(rule_id, date(2026, 11, 12))}
    assert await db_session.scalar(select(RecurringOccurrenceCoverage.id)) is not None


@pytest.mark.parametrize(
    "patch", [{"total_minor": 20000}, {"currency": "EUR"}, {"declaration": "payable"}]
)
async def test_declared_document_amount_change_requires_clear(db_session, patch: dict) -> None:
    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    bill.declaration = "declared_paid"
    bill_id = bill.id
    await db_session.commit()
    async with client_for(db_session, owner) as client:
        changed = await client.patch(
            f"/api/finance/bills/{bill_id}",
            json={"expected_version": 2, **patch},
            headers={"Idempotency-Key": "bypass"},
        )
        assert changed.status_code == 422
        cleared = await client.post(
            f"/api/finance/bills/{bill_id}/payment-declaration",
            json=command(2, "payable"),
            headers={"Idempotency-Key": "clear"},
        )
        assert cleared.status_code == 200
        if "declaration" not in patch:
            changed = await client.patch(
                f"/api/finance/bills/{bill_id}",
                json={"expected_version": 3, **patch},
                headers={"Idempotency-Key": "edit"},
            )
            assert changed.status_code == 200


async def test_generic_update_cannot_bypass_payment_declaration(db_session) -> None:
    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    bill_id = bill.id
    await db_session.commit()
    async with client_for(db_session, owner) as client:
        response = await client.patch(
            f"/api/finance/bills/{bill_id}",
            json={"expected_version": 2, "declaration": "declared_paid"},
            headers={"Idempotency-Key": "bypass"},
        )
    assert response.status_code == 422
    unchanged = await get_bill(db_session, owner, bill_id)
    assert unchanged.version == 2 and unchanged.declaration == "unknown"


async def test_audit_failure_rolls_back_declaration_and_receipt(db_session, monkeypatch) -> None:
    from app.finance import bill_declarations

    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    bill_id = bill.id
    await db_session.commit()

    async def failed_audit(*args, **kwargs):
        raise ValueError("synthetic_audit_failure")

    monkeypatch.setattr(bill_declarations, "log_event", failed_audit)
    async with client_for(db_session, owner) as client:
        response = await client.post(
            f"/api/finance/bills/{bill_id}/payment-declaration",
            json=command(),
            headers={"Idempotency-Key": "fail-audit"},
        )
    assert response.status_code == 422
    unchanged = await get_bill(db_session, owner, bill_id)
    assert unchanged.version == 2 and unchanged.declaration == "unknown"
    assert (
        await db_session.scalar(
            select(FinanceCommandReceipt.id).where(FinanceCommandReceipt.key == "fail-audit")
        )
        is None
    )
