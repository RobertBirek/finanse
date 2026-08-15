"""Tests for category budgets service."""

import uuid
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.finance.models import CategoryBudget
from app.finance.schemas import (
    AccountCreate,
    CategoryBudgetCreate,
    CategoryBudgetUpdate,
    CategoryCreate,
    PostingCreate,
    TransactionCreate,
)
from app.finance.service import (
    create_account,
    create_budget,
    create_category,
    create_transaction,
    delete_budget,
    get_budget_status,
    get_budgets,
    update_budget,
)


async def create_expense_transaction(
    db_session,
    user_id,
    account_id,
    category_id,
    *,
    amount=10_000,
    txn_date=None,
):
    return await create_transaction(
        db_session,
        user_id,
        TransactionCreate(
            transaction_date=txn_date or datetime.now(UTC).date(),
            description="Wydatek testowy",
            type="expense",
            postings=[
                PostingCreate(
                    account_id=account_id,
                    source_amount=amount,
                    source_currency="PLN",
                    base_amount_pln=amount,
                    direction="credit",
                ),
                PostingCreate(
                    category_id=category_id,
                    source_amount=amount,
                    source_currency="PLN",
                    base_amount_pln=amount,
                    direction="debit",
                ),
            ],
        ),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_category_budget_is_unique_per_user_and_category(db_session) -> None:
    user_id = uuid.uuid4()
    category = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Jedzenie", type="expense"),
    )

    budget = CategoryBudget(user_id=user_id, category_id=category.id, amount_pln=50_000)
    db_session.add(budget)
    await db_session.flush()

    assert budget.id is not None

    duplicate = CategoryBudget(user_id=user_id, category_id=category.id, amount_pln=70_000)
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_get_budget(db_session) -> None:
    user_id = uuid.uuid4()
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Zakupy", type="expense")
    )

    budget = await create_budget(
        db_session,
        user_id,
        CategoryBudgetCreate(category_id=category.id, amount_pln=120_000),
    )

    assert budget.id is not None
    assert budget.user_id == user_id
    assert budget.category_id == category.id
    assert budget.amount_pln == 120_000

    budgets = await get_budgets(db_session, user_id)
    assert [b.id for b in budgets] == [budget.id]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_budget_only_own(db_session) -> None:
    owner = uuid.uuid4()
    other = uuid.uuid4()
    category = await create_category(
        db_session, owner, CategoryCreate(name="Zakupy", type="expense")
    )
    budget = await create_budget(
        db_session,
        owner,
        CategoryBudgetCreate(category_id=category.id, amount_pln=50_000),
    )

    assert (
        await update_budget(db_session, other, budget.id, CategoryBudgetUpdate(amount_pln=80_000))
        is None
    )

    refreshed = (await get_budgets(db_session, owner))[0]
    assert refreshed.amount_pln == 50_000

    updated = await update_budget(
        db_session, owner, budget.id, CategoryBudgetUpdate(amount_pln=80_000)
    )
    assert updated is not None
    assert updated.amount_pln == 80_000


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_budget_only_own(db_session) -> None:
    owner = uuid.uuid4()
    other = uuid.uuid4()
    category = await create_category(
        db_session, owner, CategoryCreate(name="Zakupy", type="expense")
    )
    budget = await create_budget(
        db_session,
        owner,
        CategoryBudgetCreate(category_id=category.id, amount_pln=50_000),
    )

    assert await delete_budget(db_session, other, budget.id) is False
    assert len(await get_budgets(db_session, owner)) == 1

    assert await delete_budget(db_session, owner, budget.id) is True
    assert await get_budgets(db_session, owner) == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_budget_rejects_income_category(db_session) -> None:
    user_id = uuid.uuid4()
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Wyplata", type="income")
    )

    with pytest.raises(ValueError, match="expense category"):
        await create_budget(
            db_session,
            user_id,
            CategoryBudgetCreate(category_id=category.id, amount_pln=50_000),
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_budget_rejects_foreign_category(db_session) -> None:
    owner = uuid.uuid4()
    other = uuid.uuid4()
    category = await create_category(
        db_session, other, CategoryCreate(name="Prywatna", type="expense")
    )

    with pytest.raises(ValueError, match="not found"):
        await create_budget(
            db_session,
            owner,
            CategoryBudgetCreate(category_id=category.id, amount_pln=50_000),
        )


@pytest.mark.parametrize("amount_pln", [0, -1])
def test_budget_schema_rejects_non_positive_amount(amount_pln) -> None:
    with pytest.raises(ValidationError):
        CategoryBudgetCreate(category_id=uuid.uuid4(), amount_pln=amount_pln)
    with pytest.raises(ValidationError):
        CategoryBudgetUpdate(amount_pln=amount_pln)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_budget_status_empty(db_session) -> None:
    user_id = uuid.uuid4()

    status = await get_budget_status(db_session, user_id, month=8, year=2026)

    assert status.month == 8
    assert status.year == 2026
    assert status.items == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_budget_status_zero_spending(db_session) -> None:
    user_id = uuid.uuid4()
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Zdrowie", type="expense")
    )
    await create_budget(
        db_session,
        user_id,
        CategoryBudgetCreate(category_id=category.id, amount_pln=100_000),
    )

    status = await get_budget_status(db_session, user_id, month=8, year=2026)

    assert len(status.items) == 1
    item = status.items[0]
    assert item.category_id == category.id
    assert item.name == "Zdrowie"
    assert item.parent_id is None
    assert item.budget_amount_pln == 100_000
    assert item.spent_pln == 0
    assert item.remaining_pln == 100_000


@pytest.mark.integration
@pytest.mark.asyncio
async def test_budget_status_group_rolls_up_children(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(db_session, user_id, AccountCreate(name="ING", type="checking"))
    group = await create_category(
        db_session, user_id, CategoryCreate(name="Transport", type="expense")
    )
    fuel = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Paliwo", type="expense", parent_id=group.id),
    )
    await create_budget(
        db_session,
        user_id,
        CategoryBudgetCreate(category_id=group.id, amount_pln=100_000),
    )
    await create_expense_transaction(
        db_session, user_id, account.id, fuel.id, amount=30_000, txn_date=date(2026, 8, 10)
    )

    status = await get_budget_status(db_session, user_id, month=8, year=2026)

    assert len(status.items) == 1
    item = status.items[0]
    assert item.category_id == group.id
    assert item.name == "Transport"
    assert item.parent_id is None
    assert item.budget_amount_pln == 100_000
    assert item.spent_pln == 30_000
    assert item.remaining_pln == 70_000


@pytest.mark.integration
@pytest.mark.asyncio
async def test_budget_status_leaf_counts_own_spending(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(db_session, user_id, AccountCreate(name="ING", type="checking"))
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Zdrowie", type="expense")
    )
    await create_budget(
        db_session,
        user_id,
        CategoryBudgetCreate(category_id=category.id, amount_pln=100_000),
    )
    await create_expense_transaction(
        db_session, user_id, account.id, category.id, amount=40_000, txn_date=date(2026, 8, 15)
    )

    status = await get_budget_status(db_session, user_id, month=8, year=2026)

    assert len(status.items) == 1
    item = status.items[0]
    assert item.category_id == category.id
    assert item.name == "Zdrowie"
    assert item.budget_amount_pln == 100_000
    assert item.spent_pln == 40_000
    assert item.remaining_pln == 60_000


@pytest.mark.integration
@pytest.mark.asyncio
async def test_budget_status_group_counts_direct_spending(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(db_session, user_id, AccountCreate(name="ING", type="checking"))
    group = await create_category(
        db_session, user_id, CategoryCreate(name="Transport", type="expense")
    )
    await create_budget(
        db_session,
        user_id,
        CategoryBudgetCreate(category_id=group.id, amount_pln=100_000),
    )
    await create_expense_transaction(
        db_session, user_id, account.id, group.id, amount=25_000, txn_date=date(2026, 8, 12)
    )

    status = await get_budget_status(db_session, user_id, month=8, year=2026)

    assert len(status.items) == 1
    item = status.items[0]
    assert item.category_id == group.id
    assert item.budget_amount_pln == 100_000
    assert item.spent_pln == 25_000
    assert item.remaining_pln == 75_000


@pytest.mark.integration
@pytest.mark.asyncio
async def test_budget_status_sorts_items_by_name(db_session) -> None:
    user_id = uuid.uuid4()
    zakupy = await create_category(
        db_session, user_id, CategoryCreate(name="Zakupy", type="expense")
    )
    zdrowie = await create_category(
        db_session, user_id, CategoryCreate(name="Zdrowie", type="expense")
    )
    await create_budget(
        db_session,
        user_id,
        CategoryBudgetCreate(category_id=zakupy.id, amount_pln=50_000),
    )
    await create_budget(
        db_session,
        user_id,
        CategoryBudgetCreate(category_id=zdrowie.id, amount_pln=70_000),
    )

    status = await get_budget_status(db_session, user_id, month=8, year=2026)

    assert [item.name for item in status.items] == ["Zakupy", "Zdrowie"]
