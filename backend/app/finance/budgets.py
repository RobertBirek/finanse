"""Owned category budgets and monthly budget utilization."""

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.finance.dates import _month_bounds
from app.finance.entities import get_categories
from app.finance.models import Account, Category, CategoryBudget, FinancialTransaction, Posting
from app.finance.schemas import (
    BudgetStatusItem,
    BudgetStatusResponse,
    CategoryBudgetCreate,
    CategoryBudgetUpdate,
)


def category_descendants(
    children_by_parent: dict[uuid.UUID, list[uuid.UUID]], category_id: uuid.UUID
) -> set[uuid.UUID]:
    result: set[uuid.UUID] = set()
    stack = list(children_by_parent.get(category_id, []))
    while stack:
        child = stack.pop()
        if child in result:
            continue
        result.add(child)
        stack.extend(children_by_parent.get(child, []))
    return result


async def _require_expense_category(
    db: AsyncSession, user_id: uuid.UUID, category_id: uuid.UUID
) -> Category:
    result = await db.execute(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise ValueError("Budget category not found")
    if category.type != "expense":
        raise ValueError("Budget category must be an expense category")
    if not category.is_active:
        raise ValueError("Budget category is inactive")
    return category


async def create_budget(
    db: AsyncSession, user_id: uuid.UUID, data: CategoryBudgetCreate
) -> CategoryBudget:
    await _require_expense_category(db, user_id, data.category_id)
    budget = CategoryBudget(
        user_id=user_id,
        category_id=data.category_id,
        amount_pln=data.amount_pln,
    )
    db.add(budget)
    await db.flush()
    return budget


async def get_budgets(db: AsyncSession, user_id: uuid.UUID) -> list[CategoryBudget]:
    result = await db.execute(select(CategoryBudget).where(CategoryBudget.user_id == user_id))
    return list(result.scalars().all())


async def update_budget(
    db: AsyncSession, user_id: uuid.UUID, budget_id: uuid.UUID, data: CategoryBudgetUpdate
) -> CategoryBudget | None:
    result = await db.execute(
        select(CategoryBudget).where(
            CategoryBudget.id == budget_id, CategoryBudget.user_id == user_id
        )
    )
    budget = result.scalar_one_or_none()
    if budget is None:
        return None
    budget.amount_pln = data.amount_pln
    await db.flush()
    return budget


async def delete_budget(db: AsyncSession, user_id: uuid.UUID, budget_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(CategoryBudget).where(
            CategoryBudget.id == budget_id, CategoryBudget.user_id == user_id
        )
    )
    budget = result.scalar_one_or_none()
    if budget is None:
        return False
    await db.delete(budget)
    await db.flush()
    return True


async def get_budget_status(
    db: AsyncSession, user_id: uuid.UUID, month: int | None = None, year: int | None = None
) -> BudgetStatusResponse:
    selected_month, selected_year, month_start, month_end = _month_bounds(month, year)

    budgets = await get_budgets(db, user_id)
    if not budgets:
        return BudgetStatusResponse(month=selected_month, year=selected_year, items=[])

    categories = await get_categories(db, user_id)
    category_by_id = {category.id: category for category in categories}

    children_by_parent: dict[uuid.UUID, list[uuid.UUID]] = {}
    for category in categories:
        if category.parent_id is not None:
            children_by_parent.setdefault(category.parent_id, []).append(category.id)

    account_posting = aliased(Posting)
    spend_result = await db.execute(
        select(
            Posting.category_id,
            func.sum(
                case(
                    (Posting.direction == "credit", Posting.base_amount_pln),
                    else_=-Posting.base_amount_pln,
                )
            ).label("spent"),
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
            Posting.account_id.is_(None),
            Posting.category_id.is_not(None),
            Account.is_budget_account.is_(True),
        )
        .group_by(Posting.category_id)
    )
    spent_by_category = {category_id: int(spent) for category_id, spent in spend_result.all()}

    items: list[BudgetStatusItem] = []
    for budget in budgets:
        budget_category = category_by_id.get(budget.category_id)
        if budget_category is None:
            continue
        scope = category_descendants(children_by_parent, budget_category.id) | {budget_category.id}
        spent = sum(spent_by_category.get(category_id, 0) for category_id in scope)
        items.append(
            BudgetStatusItem(
                category_id=budget_category.id,
                name=budget_category.name,
                parent_id=budget_category.parent_id,
                budget_amount_pln=budget.amount_pln,
                spent_pln=spent,
                remaining_pln=budget.amount_pln - spent,
            )
        )

    items.sort(key=lambda item: item.name)
    budget_category_ids = {budget.category_id for budget in budgets}
    aggregate_items = []
    for item in items:
        parent_id = item.parent_id
        has_budget_ancestor = False
        while parent_id is not None:
            if parent_id in budget_category_ids:
                has_budget_ancestor = True
                break
            parent = category_by_id.get(parent_id)
            parent_id = parent.parent_id if parent is not None else None
        if not has_budget_ancestor:
            aggregate_items.append(item)
    return BudgetStatusResponse(
        month=selected_month,
        year=selected_year,
        items=items,
        total_budget_pln=sum(item.budget_amount_pln for item in aggregate_items),
        total_spent_pln=sum(item.spent_pln for item in aggregate_items),
        remaining_pln=sum(item.remaining_pln for item in aggregate_items),
    )
