from datetime import date

import pytest
from test_bill_payments import create_owner, setup_bill

from app.finance.bill_forecast import project_bill_cashflows
from app.finance.schemas import AccountCreate, CategoryCreate
from app.finance.service import create_account, create_category

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_paid4000_forecast6000(db_session) -> None:
    owner = await create_owner(db_session)
    account = await create_account(db_session, owner, AccountCreate(name="Konto", type="checking"))
    category = await create_category(
        db_session, owner, CategoryCreate(name="Media", type="expense")
    )
    bill = await setup_bill(db_session, owner, amount=10_000)
    bill.due_date = date(2026, 10, 31)
    bill.payment_account_id, bill.category_id, bill.declaration = account.id, category.id, "payable"
    from app.finance.models import DocumentPaymentAllocation

    # A ledger allocation is deliberately represented only by its amount in this projection test.
    # The payment-path tests cover posting eligibility.
    posting = None
    from test_bill_payments import expense

    posting, _, _ = await expense(db_session, owner, 4_000)
    db_session.add(
        DocumentPaymentAllocation(
            user_id=owner, financial_document_id=bill.id, posting_id=posting, amount_minor=4_000
        )
    )
    await db_session.flush()

    projection = await project_bill_cashflows(
        db_session, owner, today=date(2026, 10, 28), horizon_end=date(2026, 11, 27)
    )
    entry = next(item for item in projection.entries if item.financial_document_id == bill.id)
    assert (entry.amount_minor, entry.amount_pln, entry.due_date) == (
        6_000,
        6_000,
        date(2026, 10, 31),
    )


async def test_old_overdue_once_today_and_unknowns_are_explicitly_excluded(db_session) -> None:
    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    bill.due_date = date(2026, 8, 1)
    bill.declaration = "payable"
    await db_session.flush()

    projection = await project_bill_cashflows(
        db_session, owner, today=date(2026, 10, 28), horizon_end=date(2026, 11, 27)
    )
    entry = next(item for item in projection.entries if item.financial_document_id == bill.id)
    assert entry.due_date == date(2026, 10, 28)
    assert entry.included_in_forecast is False
    assert "missing_payment_account" in entry.exclusion_reasons
