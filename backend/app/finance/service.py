import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.finance.models import Account, Category, FinancialTransaction, Posting
from app.finance.schemas import (
    AccountCreate,
    AccountUpdate,
    CategoryCreate,
    CategorySpendResponse,
    CategorySummaryResponse,
    CategoryUpdate,
    FinancialSummary,
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
        balance = total_debits - total_credits

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
            Posting.direction == "credit",
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
            Posting.direction == "debit",
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
            Posting.direction == "debit",
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
