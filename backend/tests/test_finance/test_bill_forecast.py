from datetime import date

import pytest
from test_bill_payments import create_owner, setup_bill

from app.finance.bill_coverage import decide_coverage
from app.finance.bill_forecast import project_bill_cashflows
from app.finance.bills import get_bill
from app.finance.bills_schemas import CoverageDecision, MutationContext
from app.finance.schemas import (
    AccountCreate,
    CashflowSuggestion,
    CategoryCreate,
    ScheduledFinanceItemCreate,
)
from app.finance.service import create_account, create_category, create_scheduled_item

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


async def test_missing_date_fx_and_non_budget_account_have_explicit_exclusion_reasons(
    db_session,
) -> None:
    owner = await create_owner(db_session)
    account = await create_account(db_session, owner, AccountCreate(name="Konto", type="checking"))
    missing_date = await setup_bill(db_session, owner)
    missing_date.declaration = "payable"
    fx = await setup_bill(db_session, owner, currency="EUR")
    fx.due_date, fx.payment_account_id, fx.declaration = date(2026, 10, 31), account.id, "payable"
    inactive = await setup_bill(db_session, owner)
    inactive.due_date, inactive.payment_account_id, inactive.declaration = (
        date(2026, 10, 31),
        account.id,
        "payable",
    )
    account.is_active = False
    await db_session.flush()

    projection = await project_bill_cashflows(
        db_session, owner, today=date(2026, 10, 28), horizon_end=date(2026, 11, 27)
    )
    entries = {entry.financial_document_id: entry for entry in projection.entries}
    assert "missing_due_date" in entries[missing_date.id].exclusion_reasons
    assert "currency_without_pln_fx" in entries[fx.id].exclusion_reasons
    assert "payment_account_not_active_budget_pln" in entries[inactive.id].exclusion_reasons


async def test_bill_detail_uses_the_projection_exclusion_rules(db_session) -> None:
    """A detail response must not hide the reason that excludes a payable bill."""
    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner, currency="EUR")
    bill.declaration = "payable"
    detail = await get_bill(db_session, owner, bill.id)
    assert detail is not None
    assert "missing_due_date" in detail.forecast_exclusion_reasons
    assert "missing_payment_account" in detail.forecast_exclusion_reasons
    assert "currency_without_pln_fx" in detail.forecast_exclusion_reasons


async def test_detail_explains_declaration_lifecycle_account_and_unresolved_coverage(
    db_session,
) -> None:
    """Each non-inclusion branch is visible on the read-only bill response."""
    owner = await create_owner(db_session)
    today = date(2026, 10, 28)
    valid_account = await create_account(
        db_session, owner, AccountCreate(name="Valid", type="checking")
    )
    non_budget = await create_account(
        db_session,
        owner,
        AccountCreate(name="Not budget", type="checking", is_budget_account=False),
    )
    category = await create_category(
        db_session, owner, CategoryCreate(name="Coverage", type="expense")
    )
    await create_scheduled_item(
        db_session,
        owner,
        ScheduledFinanceItemCreate(
            name="Expected",
            type="expense",
            account_id=valid_account.id,
            category_id=category.id,
            currency="PLN",
            due_day=today.day,
            amount_method="fixed",
            fixed_amount_pln=1_000,
        ),
    )
    declared_paid, inactive, not_budget, unresolved, included = [
        await setup_bill(db_session, owner) for _ in range(5)
    ]
    for bill in (declared_paid, inactive, not_budget, unresolved, included):
        bill.due_date, bill.payment_account_id, bill.declaration = (
            today,
            valid_account.id,
            "payable",
        )
    declared_paid.declaration = "declared_paid"
    inactive.lifecycle = "archived"
    not_budget.payment_account_id = non_budget.id
    unresolved.category_id = category.id
    await db_session.flush()

    details = [
        await get_bill(db_session, owner, bill.id)
        for bill in (declared_paid, inactive, not_budget, unresolved, included)
    ]
    assert all(detail is not None for detail in details)
    reasons = [detail.forecast_exclusion_reasons for detail in details if detail is not None]
    assert "payment_not_payable" in reasons[0]
    assert "inactive_lifecycle" in reasons[1]
    assert "payment_account_not_active_budget_pln" in reasons[2]
    assert "coverage_unresolved" in reasons[3]
    assert reasons[4] == []


async def test_invoice12000_replaces_estimate10000_only_this_occurrence(db_session) -> None:
    owner = await create_owner(db_session)
    account = await create_account(db_session, owner, AccountCreate(name="Konto", type="checking"))
    category = await create_category(
        db_session, owner, CategoryCreate(name="Media", type="expense")
    )
    rule = await create_scheduled_item(
        db_session,
        owner,
        ScheduledFinanceItemCreate(
            name="Estimate",
            type="expense",
            account_id=account.id,
            category_id=category.id,
            currency="PLN",
            due_day=28,
            amount_method="fixed",
            fixed_amount_pln=10_000,
        ),
    )
    bill = await setup_bill(db_session, owner, amount=12_000)
    bill.due_date, bill.payment_account_id, bill.category_id, bill.declaration = (
        date(2026, 10, 31),
        account.id,
        category.id,
        "payable",
    )
    await db_session.flush()
    unresolved = await project_bill_cashflows(
        db_session, owner, today=date(2026, 10, 28), horizon_end=date(2026, 11, 27)
    )
    assert (
        "coverage_unresolved"
        in next(
            entry for entry in unresolved.entries if entry.financial_document_id == bill.id
        ).exclusion_reasons
    )
    decided = await decide_coverage(
        db_session,
        owner,
        bill.id,
        CoverageDecision(
            version=bill.version,
            choice="replace",
            scheduled_item_id=rule.id,
            occurrence_date=date(2026, 10, 28),
        ),
        context=MutationContext(idempotency_key="replace-12000"),
    )
    assert decided.recurring_decision is None
    forecast = await project_bill_cashflows(
        db_session, owner, today=date(2026, 10, 28), horizon_end=date(2026, 11, 27)
    )
    assert forecast.day_changes_pln[date(2026, 10, 31)] == -12_000
    assert (rule.id, date(2026, 10, 28)) in forecast.covered_occurrences
    assert (rule.id, date(2026, 11, 28)) not in forecast.covered_occurrences


async def test_cashflow_suggestion_validates_discriminated_sources() -> None:
    import uuid

    rule_id, document_id = uuid.uuid4(), uuid.uuid4()
    recurring = CashflowSuggestion(
        source="recurring",
        source_key="recurring:key",
        scheduled_item_id=rule_id,
        name="Rule",
        type="expense",
        due_date=date(2026, 10, 28),
        amount_pln=100,
        status="due",
        included_in_forecast=True,
    )
    document = CashflowSuggestion(
        source="financial_document",
        source_key="financial_document:key",
        financial_document_id=document_id,
        name="Bill",
        type="expense",
        due_date=date(2026, 10, 31),
        amount_pln=100,
        status="due",
        included_in_forecast=True,
    )
    assert recurring.scheduled_item_id == rule_id and document.financial_document_id == document_id
    with pytest.raises(ValueError):
        CashflowSuggestion(
            source="recurring",
            source_key="x",
            name="bad",
            type="expense",
            due_date=None,
            amount_pln=None,
            status="amount_unknown",
            included_in_forecast=False,
        )
    with pytest.raises(ValueError):
        CashflowSuggestion(
            source="financial_document",
            source_key="x",
            scheduled_item_id=rule_id,
            financial_document_id=document_id,
            name="bad",
            type="expense",
            due_date=None,
            amount_pln=None,
            status="amount_unknown",
            included_in_forecast=False,
        )
