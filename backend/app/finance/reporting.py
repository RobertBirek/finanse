"""Owned monthly finance/category reports; no ledger mutations."""

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.finance.dates import _month_bounds
from app.finance.models import Account, Category, FinancialTransaction, Posting
from app.finance.queries import get_accounts
from app.finance.schemas import (
    CategorySpendResponse,
    CategorySummaryResponse,
    CategoryTreeNode,
    FinancialSummary,
)


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
        balance_all_pln=sum(a.balance_pln for a in accounts if a.is_active),
        balance_budget_pln=sum(
            a.balance_pln for a in accounts if a.is_active and a.is_budget_account
        ),
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

    # The legacy flat fields intentionally retain their historical meaning.
    # The additive tree includes zero-total and inactive ancestors so a UI can
    # render the complete owned hierarchy while rolling each posting up once.
    tree_categories_result = await db.execute(
        select(Category)
        .where(Category.user_id == user_id, Category.type == "expense")
        .order_by(Category.name, Category.id)
    )
    tree_categories = list(tree_categories_result.scalars())
    direct_by_id = {category_id: int(total) for category_id, _, _, total in category_totals}
    children_by_parent: dict[uuid.UUID | None, list[Category]] = {}
    for tree_category in tree_categories:
        children_by_parent.setdefault(tree_category.parent_id, []).append(tree_category)

    def build_node(category: Category) -> CategoryTreeNode:
        children = [build_node(child) for child in children_by_parent.get(category.id, [])]
        direct_total = direct_by_id.get(category.id, 0)
        return CategoryTreeNode(
            category_id=category.id,
            name=category.name,
            parent_id=category.parent_id,
            is_active=category.is_active,
            direct_total_pln=direct_total,
            total_pln=direct_total + sum(child.total_pln for child in children),
            children=children,
        )

    tree = [build_node(tree_category) for tree_category in children_by_parent.get(None, [])]

    return CategorySummaryResponse(
        month=selected_month,
        year=selected_year,
        groups=groups,
        categories=categories,
        tree=tree,
    )
