import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.finance.models import Account, Category, FinancialTransaction, Posting
from app.finance.schemas import (
    AccountCreate,
    AccountUpdate,
    CategoryCreate,
    CategoryUpdate,
    FinancialSummary,
    TransactionCreate,
    TransactionUpdate,
)


async def create_account(db: AsyncSession, user_id: uuid.UUID, data: AccountCreate) -> Account:
    account = Account(user_id=user_id, **data.model_dump())
    db.add(account)
    await db.flush()
    return account


async def get_accounts(db: AsyncSession, user_id: uuid.UUID) -> list[Account]:
    result = await db.execute(
        select(Account).where(Account.user_id == user_id).order_by(Account.name)
    )
    return list(result.scalars().all())


async def get_account(db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID) -> Account | None:
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
        raise ValueError("Income/expense transactions must have at least 2 postings (source + destination)")

    if len(postings) < 2:
        raise ValueError("Transactions must have at least 2 postings")


async def create_transaction(
    db: AsyncSession, user_id: uuid.UUID, data: TransactionCreate
) -> FinancialTransaction:
    _validate_posting_sum(data.postings, data.type)

    txn = FinancialTransaction(
        user_id=user_id,
        date=data.date or date.today(),
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
            source_currency=p_data.source_currency,
            base_amount_pln=p_data.base_amount_pln,
            fx_rate=p_data.fx_rate,
            fx_rate_source=p_data.fx_rate_source,
            direction=p_data.direction,
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
    now = datetime.now(timezone.utc)
    current_month = now.month
    current_year = now.year
    month_start = date(current_year, current_month, 1)

    accounts_result = await db.execute(
        select(Account).where(Account.user_id == user_id, Account.is_active == True)
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

        account_balances.append({
            "id": str(account.id),
            "name": account.name,
            "type": account.type,
            "currency": account.currency,
            "balance_pln": balance,
        })

    income_result = await db.execute(
        select(func.coalesce(func.sum(Posting.base_amount_pln), 0))
        .join(FinancialTransaction, Posting.transaction_id == FinancialTransaction.id)
        .where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.type == "income",
            FinancialTransaction.date >= month_start,
            Posting.direction == "credit",
        )
    )
    income_total = income_result.scalar() or 0

    expense_result = await db.execute(
        select(func.coalesce(func.sum(Posting.base_amount_pln), 0))
        .join(FinancialTransaction, Posting.transaction_id == FinancialTransaction.id)
        .where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.type == "expense",
            FinancialTransaction.date >= month_start,
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
