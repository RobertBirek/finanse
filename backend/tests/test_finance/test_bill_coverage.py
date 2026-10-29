from datetime import date

import pytest
from sqlalchemy import select
from test_bill_payments import create_owner, setup_bill
from test_cashflow import scheduled_item_data

from app.finance.bill_coverage import decide_coverage, get_coverage_candidates, unlink_coverage
from app.finance.bills_schemas import CoverageDecision, MutationContext
from app.finance.models import RecurringOccurrenceCoverage
from app.finance.schemas import AccountCreate, CategoryCreate
from app.finance.service import create_account, create_category, create_scheduled_item

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _covered_bill(db_session):
    owner = await create_owner(db_session)
    account = await create_account(db_session, owner, AccountCreate(name="Konto", type="checking"))
    category = await create_category(db_session, owner, CategoryCreate(name="Prąd", type="expense"))
    item = await create_scheduled_item(
        db_session, owner, scheduled_item_data(account.id, category.id, due_day=28)
    )
    bill = await setup_bill(db_session, owner)
    bill.due_date = date(2026, 10, 31)
    bill.payment_account_id = account.id
    bill.category_id = category.id
    bill.declaration = "payable"
    await db_session.flush()
    return owner, bill, item


async def test_bill10000_vs_schedule10000_replace_once(db_session) -> None:
    owner, bill, item = await _covered_bill(db_session)
    candidates = await get_coverage_candidates(db_session, owner, bill.id)
    assert [
        (candidate.scheduled_item_id, candidate.occurrence_date) for candidate in candidates
    ] == [(item.id, date(2026, 10, 28))]

    response = await decide_coverage(
        db_session,
        owner,
        bill.id,
        CoverageDecision(
            version=bill.version,
            choice="replace",
            scheduled_item_id=item.id,
            occurrence_date=date(2026, 10, 28),
        ),
        context=MutationContext(idempotency_key="replace-once"),
    )

    assert response.coverage is not None
    assert response.coverage.occurrence_date == date(2026, 10, 28)
    assert await db_session.scalar(
        select(RecurringOccurrenceCoverage).where(
            RecurringOccurrenceCoverage.scheduled_item_id == item.id
        )
    )
    from app.finance.cashflow import get_cashflow_forecast

    forecast = await get_cashflow_forecast(db_session, owner, today=date(2026, 10, 28))
    scheduled = [entry for entry in forecast.suggestions if entry.scheduled_item_id == item.id]
    assert scheduled[0].included_in_forecast is False
    assert scheduled[0].exclusion_reasons == ["covered_by_financial_document"]
    assert any(entry.financial_document_id == bill.id for entry in forecast.suggestions)


async def test_coverage_separate_and_unlink_require_explicit_confirmation(db_session) -> None:
    owner, bill, item = await _covered_bill(db_session)
    separate = await decide_coverage(
        db_session,
        owner,
        bill.id,
        CoverageDecision(version=bill.version, choice="separate"),
        context=MutationContext(idempotency_key="separate"),
    )
    assert separate.coverage is None

    replaced = await decide_coverage(
        db_session,
        owner,
        bill.id,
        CoverageDecision(
            version=separate.version,
            choice="replace",
            scheduled_item_id=item.id,
            occurrence_date=date(2026, 10, 28),
        ),
        context=MutationContext(idempotency_key="replace"),
    )
    with pytest.raises(ValueError, match="confirmation"):
        await unlink_coverage(
            db_session,
            owner,
            bill.id,
            replaced.version,
            confirm_unlink=False,
            context=MutationContext(idempotency_key="unlink-no"),
        )
    unlinked = await unlink_coverage(
        db_session,
        owner,
        bill.id,
        replaced.version,
        confirm_unlink=True,
        context=MutationContext(idempotency_key="unlink-yes"),
    )
    assert unlinked.coverage is None
