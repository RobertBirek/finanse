"""Owned account/category mutations and serialized category hierarchy edits."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.models import Account, Category, CategoryBudget, Posting, ScheduledFinanceItem
from app.finance.queries import get_account, lock_accounts
from app.finance.schemas import AccountCreate, AccountUpdate, CategoryCreate, CategoryUpdate

SUPPORTED_CURRENCIES = {"PLN", "EUR", "USD"}


async def create_account(db: AsyncSession, user_id: uuid.UUID, data: AccountCreate) -> Account:
    currency = data.currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError("Unsupported currency")
    account = Account(user_id=user_id, **data.model_dump(exclude={"currency"}), currency=currency)
    db.add(account)
    await db.flush()
    account.can_change_currency = True
    return account


async def update_account(
    db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID, data: AccountUpdate
) -> Account | None:
    if data.currency is not None:
        await lock_accounts(db, user_id, {account_id}, exclusive=True)
    account = await get_account(db, user_id, account_id)
    if account is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    if (
        "currency" in update_data
        and update_data["currency"] != account.currency
        and not account.can_change_currency
    ):
        raise ValueError("Account currency is locked by history, schedules or import links")
    for key, value in update_data.items():
        setattr(account, key, value)
    await db.flush()
    return account


async def delete_account(db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID) -> bool:
    account = await get_account(db, user_id, account_id)
    if account is None:
        return False
    posting = await db.execute(select(Posting.id).where(Posting.account_id == account_id).limit(1))
    scheduled = await db.execute(
        select(ScheduledFinanceItem.id)
        .where(ScheduledFinanceItem.account_id == account_id)
        .limit(1)
    )
    if posting.first() is not None or scheduled.first() is not None:
        raise ValueError("Account has records; deactivate it instead of deleting")
    await db.delete(account)
    await db.flush()
    return True


async def _validate_category_parent(
    db: AsyncSession,
    user_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    category_type: str,
    category_id: uuid.UUID | None = None,
) -> None:
    # Serialize hierarchy edits so concurrent reparenting cannot introduce a cycle.
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"category-tree:{user_id}"))))
    visited = {category_id} if category_id is not None else set()
    while parent_id is not None:
        if parent_id in visited:
            raise ValueError("Category hierarchy cannot contain cycles")
        visited.add(parent_id)
        parent = (
            await db.execute(
                select(Category)
                .where(Category.id == parent_id, Category.user_id == user_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if parent is None:
            raise ValueError("Parent category not found")
        if parent.type != category_type:
            raise ValueError("Parent category type must match category type")
        parent_id = parent.parent_id


async def create_category(db: AsyncSession, user_id: uuid.UUID, data: CategoryCreate) -> Category:
    await _validate_category_parent(db, user_id, data.parent_id, data.type)
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
    if any(update_data.get(key, True) is None for key in ("name", "type", "is_active")):
        raise ValueError("Category name, type and is_active cannot be null")
    await _validate_category_parent(
        db,
        user_id,
        update_data.get("parent_id", category.parent_id),
        update_data.get("type", category.type),
        category.id,
    )
    if "type" in update_data and update_data["type"] != category.type:
        child = (
            await db.execute(
                select(Category.id)
                .where(Category.parent_id == category.id, Category.type != update_data["type"])
                .limit(1)
            )
        ).first()
        used = (
            await db.execute(select(Posting.id).where(Posting.category_id == category.id).limit(1))
        ).first()
        if child is not None or used is not None:
            raise ValueError("Cannot change the type of a category with children or postings")
    for key, value in update_data.items():
        setattr(category, key, value)
    await db.flush()
    return category


async def delete_category(db: AsyncSession, user_id: uuid.UUID, category_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    category = result.scalar_one_or_none()
    if category is None:
        return False
    posting = await db.execute(
        select(Posting.id).where(Posting.category_id == category_id).limit(1)
    )
    scheduled = await db.execute(
        select(ScheduledFinanceItem.id)
        .where(ScheduledFinanceItem.category_id == category_id)
        .limit(1)
    )
    budget = await db.execute(
        select(CategoryBudget.id).where(CategoryBudget.category_id == category_id).limit(1)
    )
    child = await db.execute(select(Category.id).where(Category.parent_id == category_id).limit(1))
    if any(result.first() is not None for result in (posting, scheduled, budget, child)):
        raise ValueError("Category has records; deactivate it instead of deleting")
    await db.delete(category)
    await db.flush()
    return True
