"""Owned monthly finance/category reports; no ledger mutations."""

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.finance.dates import _month_bounds
from app.finance.models import Account, Category, FinancialTransaction, Posting
from app.finance.queries import get_accounts
from app.finance.schemas import CategorySpendResponse, CategorySummaryResponse, FinancialSummary


async def get_financial_summary(
    db: AsyncSession, user_id: uuid.UUID, month: int | None = None, year: int | None = None
) -> FinancialSummary:
    selected_month, selected_year, month_start, month_end = _month_bounds(month, year)

    # One grouped balance query replaces two queries per active budget account.
    accounts = await get_accounts(db, user_id)
    account_balances = [
        {
            "id": str(account.id),
            "name": account.name,
            "type": account.type,
            "currency": account.currency,
            "balance_pln": account.balance_pln,
        }
        for account in accounts
        if account.is_active and account.is_budget_account
    ]

    account_posting = aliased(Posting)
    income_result = await db.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (Posting.direction == "debit", Posting.base_amount_pln),
                        else_=-Posting.base_amount_pln,
                    )
                ),
                0,
            )
        )
        .join(Category, Category.id == Posting.category_id)
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
            FinancialTransaction.type.in_(["income", "expense"]),
            Category.type == "income",
            Category.user_id == user_id,
            FinancialTransaction.date >= month_start,
            FinancialTransaction.date < month_end,
            Posting.category_id.is_not(None),
            Posting.account_id.is_(None),
            Account.is_budget_account.is_(True),
        )
    )
    income_total = income_result.scalar() or 0

    expense_result = await db.execute(
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
        .join(Category, Category.id == Posting.category_id)
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
            FinancialTransaction.type.in_(["income", "expense"]),
            Category.type == "expense",
            Category.user_id == user_id,
            FinancialTransaction.date >= month_start,
            FinancialTransaction.date < month_end,
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
        month=selected_month,
        year=selected_year,
    )


async def get_category_summary(
    db: AsyncSession, user_id: uuid.UUID, month: int | None = None, year: int | None = None
) -> CategorySummaryResponse:
    selected_month, selected_year, month_start, month_end = _month_bounds(month, year)

    account_posting = aliased(Posting)
    result = await db.execute(
        select(
            Category.id,
            Category.name,
            Category.parent_id,
            func.sum(
                case(
                    (Posting.direction == "credit", Posting.base_amount_pln),
                    else_=-Posting.base_amount_pln,
                )
            ).label("total_pln"),
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
            FinancialTransaction.type.in_(["income", "expense"]),
            Category.type == "expense",
            Category.user_id == user_id,
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
        month=selected_month,
        year=selected_year,
        groups=groups,
        categories=categories,
    )
