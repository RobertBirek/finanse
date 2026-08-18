"""Tests for account and category CRUD with deactivation."""

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.finance.schemas import (
    AccountCreate,
    AccountUpdate,
    CategoryBudgetCreate,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    PostingCreate,
    ScheduledFinanceItemCreate,
    TransactionCreate,
)
from app.finance.service import (
    create_account,
    create_budget,
    create_category,
    create_scheduled_item,
    create_transaction,
    delete_account,
    delete_category,
    get_account,
    get_categories,
    update_account,
    update_category,
)
from app.identity.router import get_current_user
from app.main import app


async def create_expense_transaction(db_session, user_id, account_id, category_id, amount=10_000):
    return await create_transaction(
        db_session,
        user_id,
        TransactionCreate(
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


def scheduled_item_data(
    account_id: uuid.UUID, category_id: uuid.UUID
) -> ScheduledFinanceItemCreate:
    return ScheduledFinanceItemCreate(
        name="Czynsz",
        type="expense",
        account_id=account_id,
        category_id=category_id,
        currency="PLN",
        due_day=5,
        amount_method="fixed",
        fixed_amount_pln=4_000,
    )


# --- delete_account ---


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_account_empty_succeeds(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(db_session, user_id, AccountCreate(name="ING", type="checking"))

    deleted = await delete_account(db_session, user_id, account.id)

    assert deleted is True
    assert await get_account(db_session, user_id, account.id) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_account_with_posting_raises_and_keeps_account(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(db_session, user_id, AccountCreate(name="ING", type="checking"))
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Jedzenie", type="expense")
    )
    await create_expense_transaction(db_session, user_id, account.id, category.id)

    with pytest.raises(ValueError, match="Account has records"):
        await delete_account(db_session, user_id, account.id)

    assert await get_account(db_session, user_id, account.id) is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_account_foreign_returns_false(db_session) -> None:
    owner = uuid.uuid4()
    other = uuid.uuid4()
    account = await create_account(db_session, owner, AccountCreate(name="ING", type="checking"))

    assert await delete_account(db_session, other, account.id) is False
    assert await get_account(db_session, owner, account.id) is not None


# --- delete_category ---


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_category_empty_succeeds(db_session) -> None:
    user_id = uuid.uuid4()
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Jedzenie", type="expense")
    )

    deleted = await delete_category(db_session, user_id, category.id)

    assert deleted is True
    assert await get_categories(db_session, user_id) == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_category_with_posting_raises_and_keeps_category(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(db_session, user_id, AccountCreate(name="ING", type="checking"))
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Jedzenie", type="expense")
    )
    await create_expense_transaction(db_session, user_id, account.id, category.id)

    with pytest.raises(ValueError, match="Category has records"):
        await delete_category(db_session, user_id, category.id)

    categories = await get_categories(db_session, user_id)
    assert [c.id for c in categories] == [category.id]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_category_with_budget_raises(db_session) -> None:
    user_id = uuid.uuid4()
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Jedzenie", type="expense")
    )
    await create_budget(
        db_session, user_id, CategoryBudgetCreate(category_id=category.id, amount_pln=50_000)
    )

    with pytest.raises(ValueError, match="Category has records"):
        await delete_category(db_session, user_id, category.id)

    assert len(await get_categories(db_session, user_id)) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_category_with_scheduled_item_raises(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(db_session, user_id, AccountCreate(name="ING", type="checking"))
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Mieszkanie", type="expense")
    )
    await create_scheduled_item(db_session, user_id, scheduled_item_data(account.id, category.id))

    with pytest.raises(ValueError, match="Category has records"):
        await delete_category(db_session, user_id, category.id)

    assert len(await get_categories(db_session, user_id)) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_category_with_child_raises(db_session) -> None:
    user_id = uuid.uuid4()
    parent = await create_category(
        db_session, user_id, CategoryCreate(name="Transport", type="expense")
    )
    await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Paliwo", type="expense", parent_id=parent.id),
    )

    with pytest.raises(ValueError, match="Category has records"):
        await delete_category(db_session, user_id, parent.id)

    assert len(await get_categories(db_session, user_id)) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_category_foreign_returns_false(db_session) -> None:
    owner = uuid.uuid4()
    other = uuid.uuid4()
    category = await create_category(
        db_session, owner, CategoryCreate(name="Jedzenie", type="expense")
    )

    assert await delete_category(db_session, other, category.id) is False
    assert len(await get_categories(db_session, owner)) == 1


# --- deactivation ---


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_category_deactivates(db_session) -> None:
    user_id = uuid.uuid4()
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Jedzenie", type="expense")
    )

    updated = await update_category(
        db_session, user_id, category.id, CategoryUpdate(is_active=False)
    )

    assert updated is not None
    await db_session.refresh(updated)
    assert updated.is_active is False
    assert CategoryResponse.model_validate(updated).is_active is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_category_is_active_api(db_session) -> None:
    user_id = uuid.uuid4()
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Jedzenie", type="expense")
    )

    async with _api_client(db_session, user_id) as client:
        response = await client.patch(
            f"/api/finance/categories/{category.id}", json={"is_active": False}
        )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_transaction_rejects_inactive_account(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(db_session, user_id, AccountCreate(name="ING", type="checking"))
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Jedzenie", type="expense")
    )
    await update_account(db_session, user_id, account.id, AccountUpdate(is_active=False))

    with pytest.raises(ValueError, match="Account is inactive"):
        await create_expense_transaction(db_session, user_id, account.id, category.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_transaction_rejects_inactive_category(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(db_session, user_id, AccountCreate(name="ING", type="checking"))
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Jedzenie", type="expense")
    )
    await update_category(db_session, user_id, category.id, CategoryUpdate(is_active=False))

    with pytest.raises(ValueError, match="Category is inactive"):
        await create_expense_transaction(db_session, user_id, account.id, category.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_budget_rejects_inactive_category(db_session) -> None:
    user_id = uuid.uuid4()
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Jedzenie", type="expense")
    )
    await update_category(db_session, user_id, category.id, CategoryUpdate(is_active=False))

    with pytest.raises(ValueError, match="Budget category is inactive"):
        await create_budget(
            db_session, user_id, CategoryBudgetCreate(category_id=category.id, amount_pln=50_000)
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_scheduled_item_rejects_inactive_category(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(db_session, user_id, AccountCreate(name="ING", type="checking"))
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Mieszkanie", type="expense")
    )
    await update_category(db_session, user_id, category.id, CategoryUpdate(is_active=False))

    with pytest.raises(ValueError, match="inactive"):
        await create_scheduled_item(
            db_session, user_id, scheduled_item_data(account.id, category.id)
        )


# --- API ---


@asynccontextmanager
async def _api_client(db_session, user_id):
    async def override_current_user():
        return SimpleNamespace(id=user_id)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_account_api_204_404_409(db_session) -> None:
    owner = uuid.uuid4()
    other = uuid.uuid4()
    account = await create_account(db_session, owner, AccountCreate(name="ING", type="checking"))
    category = await create_category(
        db_session, owner, CategoryCreate(name="Jedzenie", type="expense")
    )
    await create_expense_transaction(db_session, owner, account.id, category.id)

    async with _api_client(db_session, other) as client:
        foreign = await client.delete(f"/api/finance/accounts/{account.id}")
    assert foreign.status_code == 404

    async with _api_client(db_session, owner) as client:
        blocked = await client.delete(f"/api/finance/accounts/{account.id}")
    assert blocked.status_code == 409
    assert "deactivate" in blocked.json()["detail"]

    empty = await create_account(db_session, owner, AccountCreate(name="PKO", type="checking"))
    async with _api_client(db_session, owner) as client:
        deleted = await client.delete(f"/api/finance/accounts/{empty.id}")
        missing = await client.delete(f"/api/finance/accounts/{uuid.uuid4()}")
    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert await get_account(db_session, owner, empty.id) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_account_api_returns_updated_account(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(db_session, user_id, AccountCreate(name="ING", type="checking"))

    async with _api_client(db_session, user_id) as client:
        response = await client.patch(
            f"/api/finance/accounts/{account.id}", json={"is_active": False}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is False
    assert body["updated_at"] is not None
    assert await get_account(db_session, user_id, account.id) is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_category_api_204_404_409(db_session) -> None:
    owner = uuid.uuid4()
    other = uuid.uuid4()
    category = await create_category(
        db_session, owner, CategoryCreate(name="Jedzenie", type="expense")
    )
    await create_budget(
        db_session, owner, CategoryBudgetCreate(category_id=category.id, amount_pln=50_000)
    )

    async with _api_client(db_session, other) as client:
        foreign = await client.delete(f"/api/finance/categories/{category.id}")
    assert foreign.status_code == 404

    async with _api_client(db_session, owner) as client:
        blocked = await client.delete(f"/api/finance/categories/{category.id}")
    assert blocked.status_code == 409
    assert "deactivate" in blocked.json()["detail"]

    empty = await create_category(db_session, owner, CategoryCreate(name="Hobby", type="expense"))
    async with _api_client(db_session, owner) as client:
        deleted = await client.delete(f"/api/finance/categories/{empty.id}")
        missing = await client.delete(f"/api/finance/categories/{uuid.uuid4()}")
    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert [c.id for c in await get_categories(db_session, owner)] == [category.id]
