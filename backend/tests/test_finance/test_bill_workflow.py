"""Cross-domain financial-document workflow using synthetic PostgreSQL records only."""

from datetime import date

import pytest
from sqlalchemy import select

from app.finance.bill_coverage import decide_coverage
from app.finance.bill_payments import allocate_payment
from app.finance.bills import approve_bill, attach_source, prepare_bill
from app.finance.bills_schemas import (
    AllocationCreate,
    BillApprove,
    CoverageDecision,
    MutationContext,
)
from app.finance.cashflow import get_cashflow_forecast
from app.finance.models import DocumentPaymentAllocation, FinancialDocumentSource
from app.finance.schemas import AccountCreate, CategoryCreate, ScheduledFinanceItemCreate
from app.finance.service import create_account, create_category, create_scheduled_item
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bill_payments import create_owner, expense, setup_bill
from tests.test_finance.test_bill_sources import make_document

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_synthetic_bill_partial_then_full_removes_only_document_forecast(db_session) -> None:
    owner = await create_owner(db_session)
    account = await create_account(
        db_session, owner, AccountCreate(name="Workflow PLN", type="checking")
    )
    category = await create_category(
        db_session, owner, CategoryCreate(name="Workflow cost", type="expense")
    )
    schedule = await create_scheduled_item(
        db_session,
        owner,
        ScheduledFinanceItemCreate(
            name="Monthly 100",
            type="expense",
            account_id=account.id,
            category_id=category.id,
            currency="PLN",
            due_day=5,
            amount_method="fixed",
            fixed_amount_pln=10_000,
        ),
    )
    bill = await setup_bill(db_session, owner, 10_000)
    bill.due_date, bill.declaration, bill.payment_account_id, bill.category_id = (
        date(2026, 11, 5),
        "payable",
        account.id,
        category.id,
    )
    await db_session.flush()
    covered = await decide_coverage(
        db_session,
        owner,
        bill.id,
        CoverageDecision(
            version=bill.version,
            choice="replace",
            scheduled_item_id=schedule.id,
            occurrence_date=date(2026, 11, 5),
        ),
        context=MutationContext(idempotency_key="workflow-coverage"),
    )
    first, _, _ = await expense(db_session, owner, 4_000)
    partial = await allocate_payment(
        db_session,
        owner,
        bill.id,
        AllocationCreate(version=covered.version, posting_id=first, amount_minor=4_000),
        context=MutationContext(idempotency_key="workflow-40"),
    )
    assert (partial.remaining_minor, partial.reconciliation) == (6_000, "partial")
    forecast = await get_cashflow_forecast(db_session, owner, today=date(2026, 10, 30))
    assert [x.amount_pln for x in forecast.suggestions if x.financial_document_id == bill.id] == [
        6_000
    ]
    second, _, _ = await expense(db_session, owner, 6_000)
    full = await allocate_payment(
        db_session,
        owner,
        bill.id,
        AllocationCreate(version=partial.version, posting_id=second, amount_minor=6_000),
        context=MutationContext(idempotency_key="workflow-60"),
    )
    assert (full.remaining_minor, full.reconciliation) == (0, "full")
    forecast = await get_cashflow_forecast(db_session, owner, today=date(2026, 10, 30))
    assert not [x for x in forecast.suggestions if x.financial_document_id == bill.id]
    assert await db_session.scalar(
        select(DocumentPaymentAllocation).where(
            DocumentPaymentAllocation.financial_document_id == bill.id
        )
    )


async def test_heic_like_second_original_attaches_to_one_purchase_without_allocation(
    db_session,
) -> None:
    owner = await create_owner(db_session)
    photo, invoice = (
        await make_document(db_session, owner, "purchase.heic"),
        await make_document(db_session, owner, "invoice.pdf"),
    )
    draft = await prepare_bill(
        db_session, owner, photo.id, context=MutationContext(idempotency_key="heic-prepare")
    )
    attached = await attach_source(
        db_session,
        owner,
        draft.id,
        invoice.id,
        draft.version,
        context=MutationContext(idempotency_key="heic-attach"),
    )
    assert {source.document_id for source in attached.sources} == {photo.id, invoice.id}
    assert not list((await db_session.scalars(select(DocumentPaymentAllocation))).all())
    assert len(list((await db_session.scalars(select(FinancialDocumentSource))).all())) == 2


async def test_receipt_declared_paid_is_not_falsely_reconciled(db_session) -> None:
    owner = await create_owner(db_session)
    source = await make_document(db_session, owner, "receipt.pdf")
    draft = await prepare_bill(
        db_session, owner, source.id, context=MutationContext(idempotency_key="receipt-prepare")
    )
    receipt = await approve_bill(
        db_session,
        owner,
        draft.id,
        BillApprove(
            version=draft.version,
            kind="receipt",
            supplier_name="Receipt shop",
            description="Paid receipt",
            total_minor=1_000,
            currency="PLN",
            declaration="declared_paid",
        ),
        context=MutationContext(idempotency_key="receipt-approve"),
    )
    assert (receipt.declaration, receipt.reconciliation, receipt.paid_minor) == (
        "declared_paid",
        "none",
        0,
    )


async def test_cross_owner_original_and_bill_are_404_through_api(db_session) -> None:
    owner, other = await create_owner(db_session), await create_owner(db_session)
    document, bill = (
        await make_document(db_session, owner, "private.pdf"),
        await setup_bill(db_session, owner),
    )
    async with client_for(db_session, other) as client:
        original = await client.get(f"/api/documents/{document.id}/original")
        detail = await client.get(f"/api/finance/bills/{bill.id}")
    assert original.status_code == 404
    assert detail.status_code == 404


async def test_two_independent_sessions_approve_one_draft_once_without_ledger_entries(
    db_session,
) -> None:
    """The second real transaction waits for the row lock then sees the stale version."""
    import asyncio

    from sqlalchemy import func
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.finance.models import FinancialDocument, FinancialTransaction

    owner = await create_owner(db_session)
    source = await make_document(db_session, owner, "concurrent-approve.pdf")
    draft = await prepare_bill(
        db_session, owner, source.id, context=MutationContext(idempotency_key="concurrent-prepare")
    )
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    first_ready, release_first = asyncio.Event(), asyncio.Event()
    payload = BillApprove(
        version=draft.version,
        kind="receipt",
        supplier_name="Concurrent shop",
        description="One receipt",
        total_minor=1_000,
        currency="PLN",
        declaration="declared_paid",
    )

    async def approve(key: str, hold: bool):
        async with sessions() as session:
            try:
                async with session.begin():
                    result = await approve_bill(
                        session,
                        owner,
                        draft.id,
                        payload,
                        context=MutationContext(idempotency_key=key),
                    )
                    if hold:
                        first_ready.set()
                        await release_first.wait()
                    return result
            except (RuntimeError, ValueError) as error:
                return error

    first = asyncio.create_task(approve("concurrent-first", True))
    await first_ready.wait()
    second = asyncio.create_task(approve("concurrent-second", False))
    await asyncio.sleep(0)
    assert not second.done()
    release_first.set()
    one, two = await asyncio.gather(first, second)
    assert sum(not isinstance(item, Exception) for item in (one, two)) == 1
    persisted = await db_session.get(FinancialDocument, draft.id)
    assert persisted is not None and persisted.review == "approved" and persisted.version == 2
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 0
