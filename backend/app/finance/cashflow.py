"""Finance schedules, forecast and explicitly confirmed scheduled transactions."""

import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Literal, cast

from sqlalchemy import Select, case, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.finance.budgets import get_budget_status
from app.finance.categorization_context import digest
from app.finance.dates import _add_month, _local_today, _payday_bounds
from app.finance.models import (
    Account,
    Category,
    ConditionalRecurringObligation,
    DocumentPaymentAllocation,
    FinanceCommandReceipt,
    FinanceSettings,
    FinancialTransaction,
    Posting,
    RecurringOccurrenceCoverage,
    ScheduledFinanceItem,
)
from app.finance.queries import get_account
from app.finance.schemas import (
    CashflowBudgetSummary,
    CashflowDay,
    CashflowForecastResponse,
    CashflowSuggestion,
    FinanceSettingsUpdate,
    PostingCreate,
    ScheduledFinanceConfirmationRequest,
    ScheduledFinanceItemCreate,
    ScheduledFinanceItemUpdate,
    TransactionCreate,
)
from app.finance.transactions import create_transaction

SCHEDULE_CONFIRM_ACTION = "confirm_scheduled_occurrence"


class ScheduleConfirmationConflict(ValueError):
    pass


def _occurrence_key(item_id: uuid.UUID, due_date: date) -> str:
    return f"recurring:{item_id}:{due_date.isoformat()}"


def _scheduled_occurrences(item: ScheduledFinanceItem, *, start: date, end: date) -> list[date]:
    """Generate only the calendar occurrences that can affect this forecast."""
    if item.cadence == "annual":
        if item.due_month is None:
            raise ValueError("Annual scheduled item is missing due_month")
        return [
            date(year, item.due_month, item.due_day)
            for year in range(start.year, end.year + 1)
            if start <= date(year, item.due_month, item.due_day) <= end
        ]
    occurrences: list[date] = []
    month = start.replace(day=1)
    while month <= end:
        due_date = month.replace(day=item.due_day)
        if due_date >= start and due_date <= end:
            occurrences.append(due_date)
        month = _add_month(month)
    return occurrences


async def get_or_create_finance_settings(db: AsyncSession, user_id: uuid.UUID) -> FinanceSettings:
    result = await db.execute(select(FinanceSettings).where(FinanceSettings.user_id == user_id))
    settings = result.scalar_one_or_none()
    if settings is not None:
        return settings
    settings = FinanceSettings(user_id=user_id)
    db.add(settings)
    await db.flush()
    return settings


async def update_finance_settings(
    db: AsyncSession, user_id: uuid.UUID, data: FinanceSettingsUpdate
) -> FinanceSettings:
    settings = await get_or_create_finance_settings(db, user_id)
    update_data = data.model_dump(exclude_unset=True)
    payday_account_id = update_data.get("payday_account_id")
    if payday_account_id is not None:
        account = await get_account(db, user_id, payday_account_id)
        if account is None:
            raise ValueError("Payday account not found")
        if not account.is_budget_account:
            raise ValueError("Payday account must be a budget account")
    for key, value in update_data.items():
        setattr(settings, key, value)
    await db.flush()
    return settings


async def _validate_scheduled_item_links(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    account_id: uuid.UUID,
    category_id: uuid.UUID,
    currency: str,
    item_type: str,
) -> None:
    from app.finance.queries import lock_accounts

    account = (await lock_accounts(db, user_id, {account_id})).get(account_id)
    if account is None:
        raise ValueError("Scheduled item account not found")
    if not account.is_active or not account.is_budget_account:
        raise ValueError("Scheduled item requires an active budget account")
    if account.currency.upper() != currency.upper():
        raise ValueError("Scheduled item currency does not match account currency")
    category_result = await db.execute(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    category = category_result.scalar_one_or_none()
    if category is None:
        raise ValueError("Scheduled item category not found")
    if not category.is_active:
        raise ValueError("Scheduled item category is inactive")
    if category.type != item_type:
        raise ValueError("Scheduled item category type must match item type")


async def create_scheduled_item(
    db: AsyncSession, user_id: uuid.UUID, data: ScheduledFinanceItemCreate
) -> ScheduledFinanceItem:
    if data.cadence == "annual" and data.currency != "PLN":
        raise ValueError("annual scheduled items support PLN only")
    await _validate_scheduled_item_links(
        db,
        user_id,
        account_id=data.account_id,
        category_id=data.category_id,
        currency=data.currency,
        item_type=data.type,
    )
    item = ScheduledFinanceItem(user_id=user_id, **data.model_dump())
    db.add(item)
    await db.flush()
    return item


async def get_scheduled_items(db: AsyncSession, user_id: uuid.UUID) -> list[ScheduledFinanceItem]:
    result = await db.execute(
        select(ScheduledFinanceItem)
        .where(ScheduledFinanceItem.user_id == user_id)
        .order_by(
            ScheduledFinanceItem.cadence,
            ScheduledFinanceItem.due_month,
            ScheduledFinanceItem.due_day,
            ScheduledFinanceItem.name,
        )
    )
    return list(result.scalars().all())


async def update_scheduled_item(
    db: AsyncSession,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ScheduledFinanceItemUpdate,
) -> ScheduledFinanceItem | None:
    from app.finance.document_guards import lock_document_mutations

    await lock_document_mutations(db, user_id)
    result = await db.execute(
        select(ScheduledFinanceItem).where(
            ScheduledFinanceItem.id == item_id, ScheduledFinanceItem.user_id == user_id
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        return None
    if await db.scalar(
        select(RecurringOccurrenceCoverage.id)
        .where(
            RecurringOccurrenceCoverage.user_id == user_id,
            RecurringOccurrenceCoverage.scheduled_item_id == item.id,
        )
        .limit(1)
    ):
        raise ValueError("Scheduled item with coverage cannot be changed; unlink coverage first")
    update_data = data.model_dump(exclude_unset=True)
    cadence = update_data.get("cadence", item.cadence)
    due_month = update_data.get("due_month", item.due_month)
    if cadence == "annual" and due_month is None:
        raise ValueError("due_month is required for annual cadence")
    if cadence == "monthly" and due_month is not None:
        raise ValueError("due_month must be omitted for monthly cadence")
    currency = update_data.get("currency", item.currency).upper()
    if cadence == "annual" and currency != "PLN":
        raise ValueError("annual scheduled items support PLN only")
    amount_method = update_data.get("amount_method", item.amount_method)
    fixed_amount = update_data.get("fixed_amount_pln", item.fixed_amount_pln)
    if amount_method == "fixed" and fixed_amount is None:
        raise ValueError("fixed_amount_pln is required for fixed amount_method")
    if amount_method == "last_actual" and fixed_amount is not None:
        raise ValueError("fixed_amount_pln must be omitted for last_actual amount_method")
    await _validate_scheduled_item_links(
        db,
        user_id,
        account_id=update_data.get("account_id", item.account_id),
        category_id=update_data.get("category_id", item.category_id),
        currency=currency,
        item_type=item.type,
    )
    for key, value in update_data.items():
        setattr(item, key, value.upper() if key == "currency" and value is not None else value)
    await db.flush()
    return item


async def delete_scheduled_item(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> bool:
    from app.finance.document_guards import lock_document_mutations

    await lock_document_mutations(db, user_id)
    result = await db.execute(
        select(ScheduledFinanceItem).where(
            ScheduledFinanceItem.id == item_id, ScheduledFinanceItem.user_id == user_id
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        return False
    if await db.scalar(
        select(RecurringOccurrenceCoverage.id)
        .where(
            RecurringOccurrenceCoverage.user_id == user_id,
            RecurringOccurrenceCoverage.scheduled_item_id == item.id,
        )
        .limit(1)
    ):
        raise ValueError("Scheduled item with coverage cannot be deleted; unlink coverage first")
    await db.delete(item)
    await db.flush()
    return True


type ActualKey = tuple[str, uuid.UUID, uuid.UUID]


def _actual_key(item: ScheduledFinanceItem) -> ActualKey:
    return item.type, item.account_id, item.category_id


def _actuals_query(
    user_id: uuid.UUID,
    keys: set[ActualKey],
    *,
    start: date | None = None,
    end: date | None = None,
    exclude_transaction_ids: set[uuid.UUID] | None = None,
    latest_per_key: bool = False,
) -> Select[tuple[FinancialTransaction, int, uuid.UUID, uuid.UUID]]:
    account_posting = aliased(Posting)
    category_posting = aliased(Posting)
    account_id = account_posting.account_id
    category_id = category_posting.category_id
    key_fields = (FinancialTransaction.type, account_id, category_id)
    allocated = (
        select(1)
        .select_from(Posting)
        .join(DocumentPaymentAllocation, DocumentPaymentAllocation.posting_id == Posting.id)
        .where(Posting.transaction_id == FinancialTransaction.id)
        .correlate(FinancialTransaction)
        .exists()
    )
    stmt = (
        select(FinancialTransaction, category_posting.base_amount_pln, account_id, category_id)
        .join(account_posting, account_posting.transaction_id == FinancialTransaction.id)
        .join(category_posting, category_posting.transaction_id == FinancialTransaction.id)
        .where(
            FinancialTransaction.user_id == user_id,
            tuple_(*key_fields).in_(keys),
            account_posting.category_id.is_(None),
            category_posting.account_id.is_(None),
            category_posting.direction
            == case((FinancialTransaction.type == "expense", "credit"), else_="debit"),
            account_posting.direction
            == case((FinancialTransaction.type == "expense", "debit"), else_="credit"),
            ~allocated,
        )
    )
    if start is not None:
        stmt = stmt.where(FinancialTransaction.date >= start)
    if end is not None:
        stmt = stmt.where(FinancialTransaction.date <= end)
    if exclude_transaction_ids:
        stmt = stmt.where(FinancialTransaction.id.not_in(exclude_transaction_ids))
    if latest_per_key:
        stmt = stmt.distinct(*key_fields).order_by(*key_fields)
    stmt = stmt.order_by(
        FinancialTransaction.date.desc(),
        FinancialTransaction.created_at.desc(),
        FinancialTransaction.id.desc(),
        category_posting.id,
    )
    # The tuple membership test requires both IDs even though the columns are nullable.
    return cast("Select[tuple[FinancialTransaction, int, uuid.UUID, uuid.UUID]]", stmt)


async def _matching_actuals(
    db: AsyncSession,
    user_id: uuid.UUID,
    item: ScheduledFinanceItem,
    *,
    start: date | None = None,
    end: date | None = None,
    exclude_transaction_ids: set[uuid.UUID] | None = None,
) -> list[tuple[FinancialTransaction, int]]:
    result = await db.execute(
        _actuals_query(
            user_id,
            {_actual_key(item)},
            start=start,
            end=end,
            exclude_transaction_ids=exclude_transaction_ids,
        )
    )
    return [(transaction, amount) for transaction, amount, _, _ in result]


async def _forecast_actuals(
    db: AsyncSession,
    user_id: uuid.UUID,
    items: list[ScheduledFinanceItem],
    *,
    today: date,
    horizon_end: date,
    grace: timedelta,
    earliest_due: date,
) -> tuple[dict[ActualKey, list[tuple[FinancialTransaction, int]]], dict[ActualKey, int]]:
    recent: dict[ActualKey, list[tuple[FinancialTransaction, int]]] = defaultdict(list)
    if items:
        result = await db.execute(
            _actuals_query(
                user_id,
                {_actual_key(item) for item in items},
                start=earliest_due - grace,
                end=horizon_end + grace,
            )
        )
        for txn, amount, account_id, category_id in result:
            recent[(txn.type, account_id, category_id)].append((txn, amount))

    estimates: dict[ActualKey, int] = {}
    estimated_keys = {_actual_key(item) for item in items if item.amount_method == "last_actual"}
    if estimated_keys:
        result = await db.execute(
            _actuals_query(user_id, estimated_keys, end=today, latest_per_key=True)
        )
        estimates = {
            (txn.type, account_id, category_id): amount
            for txn, amount, account_id, category_id in result
        }
    return recent, estimates


async def _resolve_scheduled_amount(
    db: AsyncSession,
    user_id: uuid.UUID,
    item: ScheduledFinanceItem,
    today: date,
    *,
    exclude_transaction_ids: set[uuid.UUID] | None = None,
) -> int | None:
    if item.amount_method == "fixed":
        return item.fixed_amount_pln
    result = await db.execute(
        _actuals_query(
            user_id, {_actual_key(item)}, end=today, exclude_transaction_ids=exclude_transaction_ids
        ).limit(1)
    )
    actual = result.first()
    return actual[1] if actual else None


async def _budget_balance(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (Posting.direction == "credit", Posting.base_amount_pln),
                        else_=-Posting.base_amount_pln,
                    )
                ),
                0,
            )
        )
        .join(Account, Account.id == Posting.account_id)
        .where(
            Account.user_id == user_id,
            Account.is_active.is_(True),
            Account.is_budget_account.is_(True),
        )
    )
    return int(result.scalar_one())


async def get_cashflow_forecast(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    today: date | None = None,
) -> CashflowForecastResponse:
    today = today or _local_today()
    settings_result = await db.execute(
        select(FinanceSettings).where(FinanceSettings.user_id == user_id)
    )
    settings = settings_result.scalar_one_or_none()
    if settings is None:
        settings = FinanceSettings(
            user_id=user_id,
            payday_day=10,
            forecast_horizon_days=30,
            overdue_grace_days=3,
        )
    horizon_end = today + timedelta(days=settings.forecast_horizon_days - 1)
    last_payday, next_payday = _payday_bounds(today, settings.payday_day)
    grace = timedelta(days=settings.overdue_grace_days)
    items = [item for item in await get_scheduled_items(db, user_id) if item.is_active]
    conditional_obligations = list(
        (
            await db.execute(
                select(ConditionalRecurringObligation).where(
                    ConditionalRecurringObligation.user_id == user_id,
                    ConditionalRecurringObligation.is_active.is_(True),
                )
            )
        ).scalars()
    )
    from app.finance.bill_forecast import project_bill_cashflows

    bill_projection = await project_bill_cashflows(
        db, user_id, today=today, horizon_end=horizon_end
    )
    grace_start = today - grace
    occurrence_start = min(today.replace(day=1), grace_start)
    occurrences: list[tuple[ScheduledFinanceItem, date]] = []
    for item in items:
        occurrences.extend(
            (item, due_date)
            for due_date in _scheduled_occurrences(item, start=occurrence_start, end=horizon_end)
        )

    confirmed: dict[str, uuid.UUID] = {}
    if occurrences:
        confirmed = {
            key: transaction_id
            for key, transaction_id in await db.execute(
                select(FinanceCommandReceipt.key, FinancialTransaction.id)
                .join(
                    FinancialTransaction, FinancialTransaction.id == FinanceCommandReceipt.entity_id
                )
                .where(
                    FinanceCommandReceipt.user_id == user_id,
                    FinanceCommandReceipt.action == SCHEDULE_CONFIRM_ACTION,
                    FinancialTransaction.user_id == user_id,
                    FinanceCommandReceipt.key.in_(
                        [_occurrence_key(item.id, due) for item, due in occurrences]
                    ),
                )
            )
        }
    actuals, estimates = await _forecast_actuals(
        db,
        user_id,
        items,
        today=today,
        horizon_end=horizon_end,
        grace=grace,
        earliest_due=min((due for _, due in occurrences), default=today.replace(day=1)),
    )
    day_changes = {
        today + timedelta(days=offset): 0 for offset in range(settings.forecast_horizon_days)
    }
    suggestions: list[CashflowSuggestion] = []
    consumed_actuals = set(confirmed.values())
    candidates: dict[str, set[uuid.UUID]] = {}
    candidate_counts: dict[uuid.UUID, int] = defaultdict(int)
    for item, due_date in occurrences:
        occurrence_key = _occurrence_key(item.id, due_date)
        lookup_key = _actual_key(item)
        if (
            occurrence_key in confirmed
            or (item.id, due_date) in bill_projection.covered_occurrences
        ):
            continue
        amount = (
            item.fixed_amount_pln if item.amount_method == "fixed" else estimates.get(lookup_key)
        )
        matching = {
            txn.id
            for txn, actual_amount in actuals.get(lookup_key, ())
            if txn.id not in consumed_actuals
            and actual_amount == amount
            and due_date - grace <= txn.date <= due_date + grace
        }
        candidates[occurrence_key] = matching
        for transaction_id in matching:
            candidate_counts[transaction_id] += 1

    for item, due_date in occurrences:
        occurrence_key = _occurrence_key(item.id, due_date)
        key = _actual_key(item)
        amount = item.fixed_amount_pln if item.amount_method == "fixed" else estimates.get(key)
        actual_id = confirmed.get(occurrence_key)
        matching = candidates.get(occurrence_key, set())
        exclusion_reasons: list[str] = []
        included = False
        status: Literal[
            "due",
            "overdue",
            "overdue_uncertain",
            "matched_actual",
            "amount_unknown",
            "match_uncertain",
        ]
        if actual_id is not None:
            status = "matched_actual"
        elif (item.id, due_date) in bill_projection.covered_occurrences:
            status = "matched_actual"
            exclusion_reasons = ["covered_by_financial_document"]
        elif len(matching) == 1 and candidate_counts[next(iter(matching))] == 1:
            status = "matched_actual"
            actual_id = next(iter(matching))
        elif matching:
            status = "match_uncertain"
            exclusion_reasons = ["recurring_match_uncertain"]
        elif due_date < grace_start:
            status = "overdue_uncertain"
            exclusion_reasons = ["recurring_overdue_uncertain"]
        elif amount is None:
            status = "amount_unknown"
            exclusion_reasons = ["recurring_amount_unknown"]
        else:
            status = "due" if due_date >= today else "overdue"
            included = True
            direction = 1 if item.type == "income" else -1
            day_changes[max(today, due_date)] += direction * amount
        suggestions.append(
            CashflowSuggestion(
                source="recurring",
                source_key=occurrence_key,
                scheduled_item_id=item.id,
                name=item.name,
                type=cast(Literal["income", "expense"], item.type),
                due_date=due_date,
                amount_minor=amount,
                currency=item.currency,
                amount_pln=amount,
                status=status,
                included_in_forecast=included,
                actual_transaction_id=actual_id,
                exclusion_reasons=exclusion_reasons,
            )
        )

    for projected_day, change in bill_projection.day_changes_pln.items():
        if projected_day in day_changes:
            day_changes[projected_day] += change
    suggestions.extend(bill_projection.entries)
    # Conditional foreign-currency obligations are persisted declarations, not
    # transactions.  Their native amounts are intentionally excluded from PLN
    # arithmetic until an explicit FX/condition policy exists.
    from app.finance.conditional_recurring_obligations import occurrences as conditional_occurrences

    for obligation in conditional_obligations:
        for due_date in conditional_occurrences(
            obligation, start=occurrence_start, end=horizon_end
        ):
            condition_unresolved = obligation.condition_state == "unknown"
            variant = "primary" if obligation.condition_state == "satisfied" else "fallback"
            amount = getattr(obligation, f"{variant}_amount_minor", None)
            currency = getattr(obligation, f"{variant}_currency", "PLN")
            fallback_amount_unknown = not condition_unresolved and amount is None
            suggestions.append(
                CashflowSuggestion(
                    source="conditional_recurring_obligation",
                    source_key=f"conditional-recurring:{obligation.id}:{due_date.isoformat()}",
                    conditional_recurring_obligation_id=obligation.id,
                    name=obligation.name,
                    type="expense",
                    due_date=due_date,
                    amount_minor=None if condition_unresolved else amount,
                    currency=currency,
                    amount_pln=None,
                    status=(
                        "condition_unresolved"
                        if condition_unresolved
                        else (
                            "fallback_amount_unknown"
                            if fallback_amount_unknown
                            else "native_currency_forecast_unsupported"
                        )
                    ),
                    included_in_forecast=False,
                    exclusion_reasons=(
                        ["conditional_obligation_unresolved"]
                        if condition_unresolved
                        else (
                            ["conditional_obligation_fallback_amount_unknown"]
                            if fallback_amount_unknown
                            else ["conditional_obligation_native_currency_unresolved"]
                        )
                    ),
                )
            )
    opening_balance = await _budget_balance(db, user_id)
    balance = opening_balance
    days = []
    for day, change in day_changes.items():
        balance += change
        days.append(CashflowDay(date=day, projected_balance_pln=balance))
    before_payday = [day for day in days if day.date < next_payday]
    covered_until_payday = horizon_end >= next_payday - timedelta(days=1)
    omitted_expenses = [
        suggestion
        for suggestion in suggestions
        if suggestion.type == "expense"
        and suggestion.exclusion_reasons
        and suggestion.status != "matched_actual"
    ]
    omitted_before_payday = any(
        expense.due_date is None or expense.due_date < next_payday for expense in omitted_expenses
    )
    projected_before_payday = (
        before_payday[-1].projected_balance_pln if covered_until_payday else None
    )
    daily_limit = None
    if covered_until_payday and not omitted_before_payday:
        tightest_daily_limit = min(
            day.projected_balance_pln // elapsed for elapsed, day in enumerate(before_payday, 1)
        )
        daily_limit = max(0, tightest_daily_limit) if opening_balance >= 0 else 0
    lowest_before_payday = min(
        [CashflowDay(date=today, projected_balance_pln=opening_balance), *before_payday],
        key=lambda day: day.projected_balance_pln,
    )
    exclusion_reasons = sorted(
        {reason for expense in omitted_expenses for reason in expense.exclusion_reasons}
    )
    budget_status = await get_budget_status(db, user_id, today.month, today.year)
    budgets = CashflowBudgetSummary(
        total_budget_pln=budget_status.total_budget_pln,
        total_spent_pln=budget_status.total_spent_pln,
        remaining_pln=budget_status.remaining_pln,
    )
    return CashflowForecastResponse(
        last_payday=last_payday,
        next_payday=next_payday,
        opening_balance_pln=opening_balance,
        projected_balance_before_next_payday_pln=projected_before_payday,
        safe_daily_limit_pln=daily_limit,
        lowest_balance_pln=min([opening_balance, *(day.projected_balance_pln for day in days)]),
        lowest_balance_before_payday=lowest_before_payday,
        days=days,
        suggestions=sorted(
            suggestions, key=lambda suggestion: (suggestion.due_date or date.max, suggestion.name)
        ),
        budgets=budgets,
        has_excluded_obligations=bool(exclusion_reasons),
        has_excluded_obligations_before_payday=omitted_before_payday,
        excluded_obligation_reasons=exclusion_reasons,
    )


async def confirm_scheduled_item(
    db: AsyncSession,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    expected: ScheduledFinanceConfirmationRequest | None = None,
    today: date | None = None,
) -> FinancialTransaction | None:
    from app.finance.document_guards import lock_document_mutations

    await lock_document_mutations(db, user_id)
    result = await db.execute(
        select(ScheduledFinanceItem)
        .where(
            ScheduledFinanceItem.id == item_id,
            ScheduledFinanceItem.user_id == user_id,
            ScheduledFinanceItem.is_active.is_(True),
        )
        .with_for_update()
    )
    item = result.scalar_one_or_none()
    if item is None:
        return None

    account_result = await db.execute(
        select(Account)
        .where(Account.id == item.account_id, Account.user_id == user_id)
        .with_for_update()
    )
    account = account_result.scalar_one_or_none()
    if account is None:
        raise ValueError("Scheduled item account not found")
    if not account.is_active or not account.is_budget_account:
        raise ValueError("Scheduled item requires an active budget account")
    if account.currency.upper() != item.currency.upper():
        raise ValueError("Scheduled item currency does not match account currency")

    category_result = await db.execute(
        select(Category)
        .where(Category.id == item.category_id, Category.user_id == user_id)
        .with_for_update()
    )
    category = category_result.scalar_one_or_none()
    if category is None:
        raise ValueError("Scheduled item category not found")
    if category.type != item.type:
        raise ValueError("Scheduled item category type must match item type")

    if item.currency.upper() != "PLN":
        raise ValueError(
            "Scheduled item confirmation supports PLN only until source amount and FX rate are available"
        )

    effective_today = today or _local_today()
    forecast = await get_cashflow_forecast(db, user_id, today=effective_today)
    suggestion = next(
        (
            candidate
            for candidate in forecast.suggestions
            if candidate.scheduled_item_id == item.id
            and candidate.due_date is not None
            and candidate.due_date <= effective_today
            and (expected is None or candidate.due_date == expected.due_date)
        ),
        None,
    )
    if expected is not None and (
        suggestion is None
        or suggestion.status not in {"due", "overdue"}
        or suggestion.amount_pln != expected.expected_amount_pln
    ):
        raise ScheduleConfirmationConflict(
            "Pozycja się zmieniła. Odśwież prognozę i sprawdź termin oraz kwotę."
        )
    if suggestion is None:
        raise ValueError("Scheduled item has no confirmable occurrence")
    if suggestion.status not in {"due", "overdue"} or suggestion.amount_pln is None:
        raise ValueError(f"Scheduled item cannot be confirmed with status {suggestion.status}")
    if suggestion.due_date is None:
        raise ValueError("Scheduled item has no confirmable occurrence")
    covered = await db.scalar(
        select(RecurringOccurrenceCoverage.id)
        .where(
            RecurringOccurrenceCoverage.user_id == user_id,
            RecurringOccurrenceCoverage.scheduled_item_id == item.id,
            RecurringOccurrenceCoverage.occurrence_date == suggestion.due_date,
        )
        .limit(1)
    )
    if covered is not None:
        raise ValueError("Scheduled item occurrence is covered by a financial document")

    amount = suggestion.amount_pln
    account_direction = "credit" if item.type == "income" else "debit"
    category_direction = "debit" if item.type == "income" else "credit"
    transaction = await create_transaction(
        db,
        user_id,
        TransactionCreate(
            transaction_date=effective_today,
            description=f"{item.name} — {suggestion.due_date.isoformat()}",
            type=item.type,
            source="scheduled_confirmation",
            postings=[
                PostingCreate(
                    account_id=item.account_id,
                    source_amount=amount,
                    source_currency=item.currency,
                    base_amount_pln=amount,
                    fx_rate=1.0,
                    fx_rate_source="manual",
                    direction=account_direction,
                ),
                PostingCreate(
                    category_id=item.category_id,
                    source_amount=amount,
                    source_currency=item.currency,
                    base_amount_pln=amount,
                    fx_rate=1.0,
                    fx_rate_source="manual",
                    direction=category_direction,
                ),
            ],
        ),
    )
    key = _occurrence_key(item.id, suggestion.due_date)
    receipt = await db.scalar(
        select(FinanceCommandReceipt).where(
            FinanceCommandReceipt.user_id == user_id,
            FinanceCommandReceipt.action == SCHEDULE_CONFIRM_ACTION,
            FinanceCommandReceipt.key == key,
        )
    )
    confirmation = {
        "due_date": suggestion.due_date.isoformat(),
        "expected_amount_pln": amount,
    }
    if receipt is None:
        receipt = FinanceCommandReceipt(user_id=user_id, action=SCHEDULE_CONFIRM_ACTION, key=key)
        db.add(receipt)
    receipt.request_hash = digest(confirmation)
    receipt.response_json = confirmation
    receipt.entity_id = transaction.id
    await db.flush()
    return transaction
