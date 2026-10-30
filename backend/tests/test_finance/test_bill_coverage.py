from datetime import date

import pytest
from sqlalchemy import select
from test_bill_payments import create_owner, setup_bill
from test_cashflow import create_expense, scheduled_item_data

from app.finance import bill_coverage
from app.finance.bill_coverage import decide_coverage, get_coverage_candidates, unlink_coverage
from app.finance.bills import set_bill_lifecycle
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


async def test_coverage_candidate_uses_shared_scheduled_estimate(db_session) -> None:
    owner, bill, item = await _covered_bill(db_session)
    candidates = await get_coverage_candidates(db_session, owner, bill.id)

    assert candidates[0].estimate_amount_pln == item.fixed_amount_pln


async def test_coverage_candidate_uses_finance_local_today_for_last_actual(
    db_session, monkeypatch
) -> None:
    owner, bill, item = await _covered_bill(db_session)
    item.amount_method = "last_actual"
    item.fixed_amount_pln = None
    await create_expense(
        db_session, owner, item.account_id, item.category_id, 1_111, date(2026, 10, 27)
    )
    await create_expense(
        db_session, owner, item.account_id, item.category_id, 2_222, date(2026, 10, 29)
    )
    monkeypatch.setattr(bill_coverage, "_local_today", lambda: date(2026, 10, 28), raising=False)

    candidates = await get_coverage_candidates(db_session, owner, bill.id)

    assert candidates[0].estimate_amount_pln == 1_111


async def test_coverage_separate_and_unlink_require_explicit_confirmation(db_session) -> None:
    owner, bill, item = await _covered_bill(db_session)
    original_version = bill.version
    separate = await decide_coverage(
        db_session,
        owner,
        bill.id,
        CoverageDecision(version=original_version, choice="separate"),
        context=MutationContext(idempotency_key="separate"),
    )
    assert separate.coverage is None
    replay = await decide_coverage(
        db_session,
        owner,
        bill.id,
        CoverageDecision(version=original_version, choice="separate"),
        context=MutationContext(idempotency_key="separate"),
    )
    assert replay == separate

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


async def test_covered_legacy_confirm_refuses_and_lifecycle_keeps_tombstone(db_session) -> None:
    owner, bill, item = await _covered_bill(db_session)
    replaced = await decide_coverage(
        db_session,
        owner,
        bill.id,
        CoverageDecision(
            version=bill.version,
            choice="replace",
            scheduled_item_id=item.id,
            occurrence_date=date(2026, 10, 28),
        ),
        context=MutationContext(idempotency_key="covered"),
    )
    from app.finance.cashflow import confirm_scheduled_item

    with pytest.raises(ValueError):
        await confirm_scheduled_item(db_session, owner, item.id, today=date(2026, 10, 28))
    archived = await set_bill_lifecycle(
        db_session,
        owner,
        bill.id,
        "archived",
        replaced.version,
        context=MutationContext(idempotency_key="archive-covered"),
    )
    assert archived.coverage is not None
    assert (
        await db_session.scalar(
            select(RecurringOccurrenceCoverage).where(
                RecurringOccurrenceCoverage.financial_document_id == bill.id
            )
        )
        is not None
    )
    cancelled = await set_bill_lifecycle(
        db_session,
        owner,
        bill.id,
        "cancelled",
        archived.version,
        context=MutationContext(idempotency_key="cancel-covered"),
    )
    assert cancelled.coverage is not None
