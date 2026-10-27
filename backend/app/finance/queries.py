"""Owned finance reads; no ledger mutations or commits in this module."""

import uuid

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.finance.models import (
    Account,
    ActualImportMapping,
    Category,
    FinancialTransaction,
    Posting,
    ScheduledFinanceItem,
)
from app.finance.schemas import TransactionResponse, TransactionSearch, TransactionSearchResponse


def _account_rows(user_id: uuid.UUID):
    balances = (
        select(
            Posting.account_id,
            func.sum(
                case(
                    (Posting.direction == "credit", Posting.base_amount_pln),
                    else_=-Posting.base_amount_pln,
                )
            ).label("balance"),
            func.sum(
                case(
                    (Posting.direction == "credit", Posting.source_amount),
                    else_=-Posting.source_amount,
                )
            ).label("balance_source"),
        )
        .join(Account, Account.id == Posting.account_id)
        .where(Account.user_id == user_id)
        .group_by(Posting.account_id)
        .subquery()
    )
    return (
        select(
            Account,
            func.coalesce(balances.c.balance, 0),
            func.coalesce(balances.c.balance_source, 0),
            (Account.source == "manual")
            & ~select(Posting.id).where(Posting.account_id == Account.id).exists()
            & ~select(ScheduledFinanceItem.id)
            .where(ScheduledFinanceItem.account_id == Account.id)
            .exists()
            & ~select(ActualImportMapping.id)
            .where(
                ActualImportMapping.user_id == Account.user_id,
                ActualImportMapping.entity_id == Account.id,
                ActualImportMapping.entity_type == "account",
            )
            .exists(),
        )
        .outerjoin(balances, balances.c.account_id == Account.id)
        .where(Account.user_id == user_id)
    )


async def get_accounts(db: AsyncSession, user_id: uuid.UUID) -> list[Account]:
    result = await db.execute(_account_rows(user_id).order_by(Account.name, Account.id))
    accounts = []
    for account, balance, balance_source, can_change_currency in result.all():
        account._balance = int(balance)
        account._balance_source = int(balance_source)
        account.can_change_currency = bool(can_change_currency)
        accounts.append(account)
    return accounts


async def get_account(
    db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID
) -> Account | None:
    result = await db.execute(_account_rows(user_id).where(Account.id == account_id))
    row = result.one_or_none()
    if row is None:
        return None
    account, balance, balance_source, can_change_currency = row
    account._balance = int(balance)
    account._balance_source = int(balance_source)
    account.can_change_currency = bool(can_change_currency)
    return account


async def lock_accounts(
    db: AsyncSession,
    user_id: uuid.UUID,
    account_ids: set[uuid.UUID],
    *,
    exclusive: bool = False,
) -> dict[uuid.UUID, Account]:
    """Serialize currency changes against first postings/plans until commit.

    Readers may share locks; currency changes require an exclusive lock. Refresh
    existing identity-map objects after waiting, and lock transfers in ID order.
    """
    result = await db.execute(
        select(Account)
        .where(Account.user_id == user_id, Account.id.in_(account_ids))
        .order_by(Account.id)
        .with_for_update(read=not exclusive)
        .execution_options(populate_existing=True)
    )
    return {account.id: account for account in result.scalars().all()}


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


async def search_transactions(
    db: AsyncSession, user_id: uuid.UUID, filters: TransactionSearch
) -> TransactionSearchResponse:
    """Search the complete owned ledger without joining/doubling posting rows.

    Amount bounds are absolute PLN minor units of one account posting (not the
    sum of both ledger sides). Currency/account/amount must match that same leg.
    """
    txn = FinancialTransaction
    account_leg: list[ColumnElement[bool]] = [Posting.account_id.is_not(None)]
    if filters.budget_accounts_only:
        account_leg.append(
            Posting.account_id.in_(
                select(Account.id).where(
                    Account.user_id == user_id, Account.is_budget_account.is_(True)
                )
            )
        )
    if filters.account_id:
        account_leg.append(Posting.account_id == filters.account_id)
    if filters.currency:
        account_leg.append(Posting.source_currency == filters.currency)
    if filters.min_amount_pln is not None:
        account_leg.append(func.abs(Posting.base_amount_pln) >= filters.min_amount_pln)
    if filters.max_amount_pln is not None:
        account_leg.append(func.abs(Posting.base_amount_pln) <= filters.max_amount_pln)
    conditions = [
        txn.user_id == user_id,
        select(Posting.id).where(Posting.transaction_id == txn.id, *account_leg).exists(),
    ]
    if filters.category_id:
        category_ids = select(Category.id).where(
            Category.id == filters.category_id, Category.user_id == user_id
        )
        if filters.include_descendants:
            descendants = category_ids.cte("category_descendants", recursive=True)
            descendants = descendants.union_all(
                select(Category.id).where(
                    Category.parent_id == descendants.c.id, Category.user_id == user_id
                )
            )
            category_ids = select(descendants.c.id)
        conditions.append(
            select(Posting.id)
            .where(
                Posting.transaction_id == txn.id,
                Posting.category_id.in_(category_ids),
            )
            .exists()
        )
    if filters.date_from:
        conditions.append(txn.date >= filters.date_from)
    if filters.date_to:
        conditions.append(txn.date <= filters.date_to)
    if filters.type:
        conditions.append(txn.type == filters.type)
    if filters.q:
        # autoescape treats user %, _ and / literally; values remain bound parameters.
        conditions.append(
            or_(
                txn.description.icontains(filters.q, autoescape=True),
                select(Posting.id)
                .join(Account, Posting.account_id == Account.id)
                .where(
                    Posting.transaction_id == txn.id,
                    Account.user_id == user_id,
                    Account.name.icontains(filters.q, autoescape=True),
                )
                .exists(),
                select(Posting.id)
                .join(Category, Posting.category_id == Category.id)
                .where(
                    Posting.transaction_id == txn.id,
                    Category.user_id == user_id,
                    Category.name.icontains(filters.q, autoescape=True),
                )
                .exists(),
            )
        )
    total = await db.scalar(select(func.count()).select_from(txn).where(*conditions))
    result = await db.execute(
        select(txn)
        .options(selectinload(txn.postings))
        .where(*conditions)
        .order_by(txn.date.desc(), txn.created_at.desc(), txn.id.desc())
        .limit(filters.limit)
        .offset(filters.offset)
    )
    return TransactionSearchResponse(
        items=[TransactionResponse.model_validate(txn) for txn in result.scalars().all()],
        total=total or 0,
        limit=filters.limit,
        offset=filters.offset,
    )


async def get_transaction(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID
) -> FinancialTransaction | None:
    result = await db.execute(
        select(FinancialTransaction)
        .options(selectinload(FinancialTransaction.postings))
        .where(FinancialTransaction.id == transaction_id, FinancialTransaction.user_id == user_id)
    )
    return result.scalar_one_or_none()
