import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Literal, cast

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.finance.models import (
    Account,
    Category,
    FinanceSettings,
    FinancialTransaction,
    Posting,
    ScheduledFinanceItem,
)
from app.finance.schemas import (
    AccountCreate,
    AccountUpdate,
    CashflowDay,
    CashflowForecastResponse,
    CashflowSuggestion,
    CategoryCreate,
    CategorySpendResponse,
    CategorySummaryResponse,
    CategoryUpdate,
    FinanceSettingsUpdate,
    FinancialSummary,
    ScheduledFinanceItemCreate,
    ScheduledFinanceItemUpdate,
    TransactionCreate,
    TransactionUpdate,
)

SUPPORTED_CURRENCIES = {"PLN", "EUR", "USD"}


def _local_today() -> date:
    """Keep transaction dates aligned with the user's local calendar day."""
    return datetime.now(UTC).astimezone().date()


async def create_account(db: AsyncSession, user_id: uuid.UUID, data: AccountCreate) -> Account:
    currency = data.currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError("Unsupported currency")
    account = Account(user_id=user_id, **data.model_dump(exclude={"currency"}), currency=currency)
    db.add(account)
    await db.flush()
    return account


async def get_accounts(db: AsyncSession, user_id: uuid.UUID) -> list[Account]:
    """Get accounts with computed balance (credits - debits in PLN)."""
    from sqlalchemy import case

    balance_subq = (
        select(
            Posting.account_id,
            func.sum(
                case(
                    (Posting.direction == "credit", Posting.base_amount_pln),
                    else_=-Posting.base_amount_pln,
                )
            ).label("balance"),
        )
        .group_by(Posting.account_id)
        .subquery()
    )

    result = await db.execute(
        select(Account, func.coalesce(balance_subq.c.balance, 0))
        .outerjoin(balance_subq, Account.id == balance_subq.c.account_id)
        .where(Account.user_id == user_id)
        .order_by(Account.name)
    )
    rows = result.all()
    accounts = []
    for account, balance in rows:
        account._balance = int(balance)
        accounts.append(account)
    return accounts


async def get_account(
    db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID
) -> Account | None:
    result = await db.execute(
        select(Account).where(Account.id == account_id, Account.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_account(
    db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID, data: AccountUpdate
) -> Account | None:
    account = await get_account(db, user_id, account_id)
    if account is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(account, key, value)
    await db.flush()
    return account


async def create_category(db: AsyncSession, user_id: uuid.UUID, data: CategoryCreate) -> Category:
    category = Category(user_id=user_id, **data.model_dump())
    db.add(category)
    await db.flush()
    return category


async def get_categories(db: AsyncSession, user_id: uuid.UUID) -> list[Category]:
    result = await db.execute(
        select(Category).where(Category.user_id == user_id).order_by(Category.name)
    )
    return list(result.scalars().all())


async def update_category(
    db: AsyncSession, user_id: uuid.UUID, category_id: uuid.UUID, data: CategoryUpdate
) -> Category | None:
    result = await db.execute(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    category = result.scalar_one_or_none()
    if category is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(category, key, value)
    await db.flush()
    return category


def _validate_posting_sum(postings: list, txn_type: str) -> None:
    """Validate that sum of postings' base_amount_pln equals 0, respecting debit/credit signs."""
    total = 0
    for p in postings:
        signed_amount = p.base_amount_pln if p.direction == "debit" else -p.base_amount_pln
        total += signed_amount

    if total != 0:
        raise ValueError(
            f"Sum of posting base amounts must equal 0 (got {total}). "
            "Debits = Credits (double-entry accounting invariant)."
        )

    if txn_type in ("income", "expense") and len(postings) < 2:
        raise ValueError(
            "Income/expense transactions must have at least 2 postings (source + destination)"
        )

    if len(postings) < 2:
        raise ValueError("Transactions must have at least 2 postings")


async def _validate_transaction_postings(
    db: AsyncSession, user_id: uuid.UUID, postings: list, txn_type: str
) -> None:
    account_ids = {posting.account_id for posting in postings if posting.account_id is not None}
    accounts: dict[uuid.UUID, Account] = {}
    if account_ids:
        account_result = await db.execute(
            select(Account).where(Account.user_id == user_id, Account.id.in_(account_ids))
        )
        accounts = {account.id: account for account in account_result.scalars().all()}

    category_ids = {posting.category_id for posting in postings if posting.category_id is not None}
    categories: dict[uuid.UUID, Category] = {}
    if category_ids:
        category_result = await db.execute(
            select(Category).where(Category.user_id == user_id, Category.id.in_(category_ids))
        )
        categories = {category.id: category for category in category_result.scalars().all()}

    for posting in postings:
        if posting.account_id is None and posting.category_id is None:
            raise ValueError("Posting must have at least an account or category")
        account = accounts.get(posting.account_id) if posting.account_id is not None else None
        if posting.account_id is not None and account is None:
            raise ValueError("Account not found")
        if posting.category_id is not None and posting.category_id not in categories:
            raise ValueError("Category not found")

        source_currency = str(posting.source_currency).upper()
        if source_currency not in SUPPORTED_CURRENCIES:
            raise ValueError("Unsupported currency")
        if account is not None:
            account_currency = str(account.currency).upper()
            if account_currency not in SUPPORTED_CURRENCIES:
                raise ValueError("Unsupported currency")
            if source_currency != account_currency:
                raise ValueError(
                    f"Posting currency {source_currency} does not match account currency "
                    f"{account_currency}"
                )
        if posting.source_amount <= 0 or posting.base_amount_pln <= 0:
            raise ValueError("Posting amounts must be positive")
        if posting.fx_rate <= 0:
            raise ValueError("FX rate must be positive")

    if txn_type not in {"income", "expense"}:
        return

    account_side_postings = [
        posting
        for posting in postings
        if posting.account_id is not None and posting.category_id is None
    ]
    if len(account_side_postings) != 1:
        raise ValueError("Income/expense transactions require exactly one account-side posting")

    account = accounts[account_side_postings[0].account_id]
    for posting in postings:
        if posting.account_id is None and posting.category_id is not None:
            posting.is_budget_impact = account.is_budget_account


async def create_transaction(
    db: AsyncSession, user_id: uuid.UUID, data: TransactionCreate
) -> FinancialTransaction:
    _validate_posting_sum(data.postings, data.type)
    await _validate_transaction_postings(db, user_id, data.postings, data.type)

    txn = FinancialTransaction(
        user_id=user_id,
        date=data.transaction_date or _local_today(),
        description=data.description,
        type=data.type,
        is_pending=data.is_pending,
        project_id=data.project_id,
        source=data.source,
    )
    db.add(txn)
    await db.flush()

    for p_data in data.postings:
        posting = Posting(
            transaction_id=txn.id,
            account_id=p_data.account_id,
            category_id=p_data.category_id,
            source_amount=p_data.source_amount,
            source_currency=p_data.source_currency.upper(),
            base_amount_pln=p_data.base_amount_pln,
            fx_rate=p_data.fx_rate,
            fx_rate_source=p_data.fx_rate_source,
            direction=p_data.direction,
            is_budget_impact=p_data.is_budget_impact,
        )
        db.add(posting)

    await db.flush()

    result = await db.execute(
        select(FinancialTransaction)
        .options(selectinload(FinancialTransaction.postings))
        .where(FinancialTransaction.id == txn.id)
    )
    return result.scalar_one()


async def get_transactions(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    txn_type: str | None = None,
) -> list[FinancialTransaction]:
    stmt = (
        select(FinancialTransaction)
        .options(selectinload(FinancialTransaction.postings))
        .where(FinancialTransaction.user_id == user_id)
        .order_by(FinancialTransaction.date.desc(), FinancialTransaction.created_at.desc())
    )
    if txn_type:
        stmt = stmt.where(FinancialTransaction.type == txn_type)

    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_transaction(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID
) -> FinancialTransaction | None:
    result = await db.execute(
        select(FinancialTransaction)
        .options(selectinload(FinancialTransaction.postings))
        .where(FinancialTransaction.id == transaction_id, FinancialTransaction.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_transaction(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID, data: TransactionUpdate
) -> FinancialTransaction | None:
    txn = await get_transaction(db, user_id, transaction_id)
    if txn is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(txn, key, value)
    await db.flush()
    return txn


async def get_financial_summary(db: AsyncSession, user_id: uuid.UUID) -> FinancialSummary:
    now = datetime.now(UTC)
    current_month = now.month
    current_year = now.year
    month_start = date(current_year, current_month, 1)

    accounts_result = await db.execute(
        select(Account).where(
            Account.user_id == user_id,
            Account.is_active.is_(True),
            Account.is_budget_account.is_(True),
        )
    )
    accounts = list(accounts_result.scalars().all())

    account_balances = []
    for account in accounts:
        debit_result = await db.execute(
            select(func.coalesce(func.sum(Posting.base_amount_pln), 0)).where(
                Posting.account_id == account.id,
                Posting.direction == "debit",
            )
        )
        credit_result = await db.execute(
            select(func.coalesce(func.sum(Posting.base_amount_pln), 0)).where(
                Posting.account_id == account.id,
                Posting.direction == "credit",
            )
        )
        total_debits = debit_result.scalar() or 0
        total_credits = credit_result.scalar() or 0
        balance = int(total_credits - total_debits)

        account_balances.append(
            {
                "id": str(account.id),
                "name": account.name,
                "type": account.type,
                "currency": account.currency,
                "balance_pln": balance,
            }
        )

    account_posting = aliased(Posting)
    income_result = await db.execute(
        select(func.coalesce(func.sum(Posting.base_amount_pln), 0))
        .join(FinancialTransaction, Posting.transaction_id == FinancialTransaction.id)
        .join(
            account_posting,
            (account_posting.transaction_id == FinancialTransaction.id)
            & account_posting.account_id.is_not(None)
            & account_posting.category_id.is_(None),
        )
        .join(Account, Account.id == account_posting.account_id)
        .where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.type == "income",
            FinancialTransaction.date >= month_start,
            Posting.category_id.is_not(None),
            Posting.account_id.is_(None),
            Account.is_budget_account.is_(True),
        )
    )
    income_total = income_result.scalar() or 0

    expense_result = await db.execute(
        select(func.coalesce(func.sum(Posting.base_amount_pln), 0))
        .join(FinancialTransaction, Posting.transaction_id == FinancialTransaction.id)
        .join(
            account_posting,
            (account_posting.transaction_id == FinancialTransaction.id)
            & account_posting.account_id.is_not(None)
            & account_posting.category_id.is_(None),
        )
        .join(Account, Account.id == account_posting.account_id)
        .where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.type == "expense",
            FinancialTransaction.date >= month_start,
            Posting.category_id.is_not(None),
            Posting.account_id.is_(None),
            Account.is_budget_account.is_(True),
        )
    )
    expense_total = expense_result.scalar() or 0

    return FinancialSummary(
        accounts=account_balances,
        income_total_pln=income_total,
        expense_total_pln=expense_total,
        net_total_pln=income_total - expense_total,
        month=current_month,
        year=current_year,
    )


async def get_category_summary(db: AsyncSession, user_id: uuid.UUID) -> CategorySummaryResponse:
    now = datetime.now(UTC)
    month_start = date(now.year, now.month, 1)
    month_end = date(now.year + (now.month == 12), (now.month % 12) + 1, 1)

    account_posting = aliased(Posting)
    result = await db.execute(
        select(
            Category.id,
            Category.name,
            Category.parent_id,
            func.sum(Posting.base_amount_pln).label("total_pln"),
        )
        .join(Posting, Posting.category_id == Category.id)
        .join(FinancialTransaction, Posting.transaction_id == FinancialTransaction.id)
        .join(
            account_posting,
            (account_posting.transaction_id == FinancialTransaction.id)
            & account_posting.account_id.is_not(None)
            & account_posting.category_id.is_(None),
        )
        .join(Account, Account.id == account_posting.account_id)
        .where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.type == "expense",
            FinancialTransaction.date >= month_start,
            FinancialTransaction.date < month_end,
            Posting.account_id.is_(None),
            Account.is_budget_account.is_(True),
        )
        .group_by(Category.id, Category.name, Category.parent_id)
        .order_by(Category.name)
    )
    category_totals = result.all()

    categories = [
        CategorySpendResponse(
            category_id=category_id,
            name=name,
            parent_id=parent_id,
            total_pln=int(total_pln),
        )
        for category_id, name, parent_id, total_pln in category_totals
    ]
    group_totals: dict[uuid.UUID, int] = {}
    for category in categories:
        if category.parent_id is not None:
            group_totals[category.parent_id] = (
                group_totals.get(category.parent_id, 0) + category.total_pln
            )

    groups_result = await db.execute(
        select(Category.id, Category.name, Category.parent_id)
        .where(Category.user_id == user_id, Category.id.in_(group_totals))
        .order_by(Category.name)
    )
    groups = [
        CategorySpendResponse(
            category_id=category_id,
            name=name,
            parent_id=parent_id,
            total_pln=group_totals[category_id],
        )
        for category_id, name, parent_id in groups_result.all()
    ]

    return CategorySummaryResponse(
        month=now.month,
        year=now.year,
        groups=groups,
        categories=categories,
    )


def _add_month(value: date, months: int = 1) -> date:
    month = value.month - 1 + months
    return date(value.year + month // 12, month % 12 + 1, value.day)


def _payday_bounds(today: date, payday_day: int) -> tuple[date, date]:
    current_payday = date(today.year, today.month, payday_day)
    if today >= current_payday:
        return current_payday, _add_month(current_payday)
    return _add_month(current_payday, -1), current_payday


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
    account = await get_account(db, user_id, account_id)
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
    if category.type != item_type:
        raise ValueError("Scheduled item category type must match item type")


async def create_scheduled_item(
    db: AsyncSession, user_id: uuid.UUID, data: ScheduledFinanceItemCreate
) -> ScheduledFinanceItem:
    await _validate_scheduled_item_links(
        db,
        user_id,
        account_id=data.account_id,
        category_id=data.category_id,
        currency=data.currency,
        item_type=data.type,
    )
    item = ScheduledFinanceItem(user_id=user_id, cadence="monthly", **data.model_dump())
    db.add(item)
    await db.flush()
    return item


async def get_scheduled_items(db: AsyncSession, user_id: uuid.UUID) -> list[ScheduledFinanceItem]:
    result = await db.execute(
        select(ScheduledFinanceItem)
        .where(ScheduledFinanceItem.user_id == user_id)
        .order_by(ScheduledFinanceItem.due_day, ScheduledFinanceItem.name)
    )
    return list(result.scalars().all())


async def update_scheduled_item(
    db: AsyncSession,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ScheduledFinanceItemUpdate,
) -> ScheduledFinanceItem | None:
    result = await db.execute(
        select(ScheduledFinanceItem).where(
            ScheduledFinanceItem.id == item_id, ScheduledFinanceItem.user_id == user_id
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
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
        currency=update_data.get("currency", item.currency).upper(),
        item_type=item.type,
    )
    for key, value in update_data.items():
        setattr(item, key, value.upper() if key == "currency" and value is not None else value)
    await db.flush()
    return item


async def _matching_actuals(
    db: AsyncSession,
    user_id: uuid.UUID,
    item: ScheduledFinanceItem,
    *,
    start: date | None = None,
    end: date | None = None,
) -> list[tuple[FinancialTransaction, int]]:
    account_posting = aliased(Posting)
    category_posting = aliased(Posting)
    stmt = (
        select(FinancialTransaction, category_posting.base_amount_pln)
        .join(account_posting, account_posting.transaction_id == FinancialTransaction.id)
        .join(category_posting, category_posting.transaction_id == FinancialTransaction.id)
        .where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.type == item.type,
            account_posting.account_id == item.account_id,
            account_posting.category_id.is_(None),
            category_posting.account_id.is_(None),
            category_posting.category_id == item.category_id,
        )
        .order_by(FinancialTransaction.date.desc(), FinancialTransaction.created_at.desc())
    )
    if start is not None:
        stmt = stmt.where(FinancialTransaction.date >= start)
    if end is not None:
        stmt = stmt.where(FinancialTransaction.date <= end)
    result = await db.execute(stmt)
    return [(transaction, int(amount)) for transaction, amount in result.all()]


async def _resolve_scheduled_amount(
    db: AsyncSession, user_id: uuid.UUID, item: ScheduledFinanceItem, today: date
) -> int | None:
    if item.amount_method == "fixed":
        return item.fixed_amount_pln
    actuals = await _matching_actuals(db, user_id, item, end=today)
    return actuals[0][1] if actuals else None


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
    items = [item for item in await get_scheduled_items(db, user_id) if item.is_active]
    day_changes = {
        today + timedelta(days=offset): 0 for offset in range(settings.forecast_horizon_days)
    }
    suggestions: list[CashflowSuggestion] = []

    month = date(today.year, today.month, 1)
    while month <= horizon_end:
        for item in items:
            due_date = date(month.year, month.month, item.due_day)
            if due_date > horizon_end:
                continue
            amount = await _resolve_scheduled_amount(db, user_id, item, today)
            actual_id = None
            matching = await _matching_actuals(
                db,
                user_id,
                item,
                start=due_date - timedelta(days=settings.overdue_grace_days),
                end=due_date + timedelta(days=settings.overdue_grace_days),
            )
            matching = [match for match in matching if amount is not None and match[1] == amount]
            status: Literal[
                "due", "overdue", "overdue_uncertain", "matched_actual", "amount_unknown"
            ]
            if matching:
                status = "matched_actual"
                included = False
                actual_id = matching[0][0].id
            elif due_date < today - timedelta(days=settings.overdue_grace_days):
                status = "overdue_uncertain"
                included = False
            elif amount is None:
                status = "amount_unknown"
                included = False
            else:
                status = "due" if due_date >= today else "overdue"
                included = True
                effective_date = max(today, due_date)
                if effective_date <= horizon_end:
                    direction = 1 if item.type == "income" else -1
                    day_changes[effective_date] += direction * amount
            suggestions.append(
                CashflowSuggestion(
                    scheduled_item_id=item.id,
                    name=item.name,
                    type=cast(Literal["income", "expense"], item.type),
                    due_date=due_date,
                    amount_pln=amount,
                    status=status,
                    included_in_forecast=included,
                    actual_transaction_id=actual_id,
                )
            )
        month = _add_month(month)

    opening_balance = await _budget_balance(db, user_id)
    balance = opening_balance
    days = []
    for day, change in day_changes.items():
        balance += change
        days.append(CashflowDay(date=day, projected_balance_pln=balance))
    _, next_payday = _payday_bounds(today, settings.payday_day)
    before_payday = [day.projected_balance_pln for day in days if day.date < next_payday]
    projected_before_payday = before_payday[-1] if before_payday else opening_balance
    remaining_days = max((next_payday - today).days, 1)
    return CashflowForecastResponse(
        last_payday=_payday_bounds(today, settings.payday_day)[0],
        next_payday=next_payday,
        opening_balance_pln=opening_balance,
        projected_balance_before_next_payday_pln=projected_before_payday,
        safe_daily_limit_pln=max(projected_before_payday, 0) // remaining_days,
        lowest_balance_pln=min([opening_balance, *(day.projected_balance_pln for day in days)]),
        days=days,
        suggestions=sorted(
            suggestions, key=lambda suggestion: (suggestion.due_date, suggestion.name)
        ),
    )
