import asyncio
import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import get_db
from app.finance import service as finance_service
from app.finance.models import FinanceSettings, FinancialTransaction, Posting
from app.finance.schemas import (
    AccountCreate,
    CategoryBudgetCreate,
    CategoryCreate,
    PostingCreate,
    ScheduledFinanceItemCreate,
    TransactionCreate,
)
from app.finance.service import (
    confirm_scheduled_item,
    create_account,
    create_budget,
    create_category,
    create_scheduled_item,
    create_transaction,
    delete_scheduled_item,
    get_cashflow_forecast,
    get_scheduled_items,
)
from app.identity.router import get_current_user
from app.main import app


def scheduled_item_data(account_id: uuid.UUID, category_id: uuid.UUID, **overrides: object):
    data: dict[str, object] = {
        "name": "Czynsz",
        "type": "expense",
        "account_id": account_id,
        "category_id": category_id,
        "currency": "PLN",
        "due_day": 5,
        "amount_method": "fixed",
        "fixed_amount_pln": 4_000,
    }
    data.update(overrides)
    return ScheduledFinanceItemCreate(**data)


def test_fixed_schedule_requires_an_amount() -> None:
    with pytest.raises(ValueError, match="fixed_amount_pln"):
        scheduled_item_data(uuid.uuid4(), uuid.uuid4(), fixed_amount_pln=None)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_schedule_rejects_an_offbudget_account(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(
        db_session,
        user_id,
        AccountCreate(name="Kredyt", type="credit", is_budget_account=False),
    )
    category = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Czynsz", type="expense"),
    )

    with pytest.raises(ValueError, match="budget account"):
        await create_scheduled_item(
            db_session, user_id, scheduled_item_data(account.id, category.id)
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_forecast_marks_an_item_uncertain_after_three_overdue_days(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(
        db_session,
        user_id,
        AccountCreate(name="Konto", type="checking"),
    )
    category = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Czynsz", type="expense"),
    )
    await create_scheduled_item(
        db_session,
        user_id,
        scheduled_item_data(account.id, category.id, due_day=10),
    )

    forecast = await get_cashflow_forecast(db_session, user_id, today=date(2026, 8, 14))

    assert forecast.suggestions[0].status == "overdue_uncertain"
    assert forecast.suggestions[0].included_in_forecast is False
    assert await row_count(db_session, FinanceSettings) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_forecast_matches_actual_before_marking_an_overdue_item_uncertain(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(
        db_session,
        user_id,
        AccountCreate(name="Konto", type="checking"),
    )
    category = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Czynsz", type="expense"),
    )
    actual = await create_transaction(
        db_session,
        user_id,
        TransactionCreate(
            transaction_date=date(2026, 8, 12),
            description="Czynsz sierpień",
            type="expense",
            postings=[
                PostingCreate(
                    account_id=account.id,
                    source_amount=4_000,
                    base_amount_pln=4_000,
                    direction="credit",
                ),
                PostingCreate(
                    category_id=category.id,
                    source_amount=4_000,
                    base_amount_pln=4_000,
                    direction="debit",
                ),
            ],
        ),
    )
    await create_scheduled_item(
        db_session,
        user_id,
        scheduled_item_data(account.id, category.id, due_day=10),
    )
    transaction_count = await row_count(db_session, FinancialTransaction)
    posting_count = await row_count(db_session, Posting)

    forecast = await get_cashflow_forecast(db_session, user_id, today=date(2026, 8, 14))

    suggestion = forecast.suggestions[0]
    assert suggestion.status == "matched_actual"
    assert suggestion.actual_transaction_id == actual.id
    assert suggestion.included_in_forecast is False
    assert await row_count(db_session, FinancialTransaction) == transaction_count
    assert await row_count(db_session, Posting) == posting_count


@pytest.mark.integration
@pytest.mark.asyncio
async def test_forecast_uses_budget_balance_fixed_and_last_actual_amounts(db_session) -> None:
    user_id = uuid.uuid4()
    budget_account = await create_account(
        db_session,
        user_id,
        AccountCreate(name="Konto", type="checking"),
    )
    offbudget_account = await create_account(
        db_session,
        user_id,
        AccountCreate(name="Kredyt", type="credit", is_budget_account=False),
    )
    income_category = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Wypłata", type="income"),
    )
    rent_category = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Czynsz", type="expense"),
    )
    phone_category = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Telefon", type="expense"),
    )
    await create_income(db_session, user_id, budget_account.id, income_category.id, 10_000)
    await create_income(db_session, user_id, offbudget_account.id, income_category.id, 50_000)
    await create_expense(
        db_session,
        user_id,
        budget_account.id,
        phone_category.id,
        1_234,
        date(2026, 7, 16),
    )
    await create_scheduled_item(
        db_session,
        user_id,
        scheduled_item_data(budget_account.id, rent_category.id, due_day=16),
    )
    await create_scheduled_item(
        db_session,
        user_id,
        scheduled_item_data(
            budget_account.id,
            phone_category.id,
            name="Telefon",
            due_day=17,
            amount_method="last_actual",
            fixed_amount_pln=None,
        ),
    )

    forecast = await get_cashflow_forecast(db_session, user_id, today=date(2026, 8, 14))

    assert forecast.opening_balance_pln == 8_766
    assert forecast.lowest_balance_pln == 3_532
    assert [(item.name, item.amount_pln) for item in forecast.suggestions] == [
        ("Czynsz", 4_000),
        ("Telefon", 1_234),
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_forecast_includes_budget_summary(db_session) -> None:
    user_id = uuid.uuid4()
    food = await create_category(
        db_session, user_id, CategoryCreate(name="Jedzenie", type="expense")
    )
    health = await create_category(
        db_session, user_id, CategoryCreate(name="Zdrowie", type="expense")
    )
    await create_budget(
        db_session, user_id, CategoryBudgetCreate(category_id=food.id, amount_pln=100_000)
    )
    await create_budget(
        db_session, user_id, CategoryBudgetCreate(category_id=health.id, amount_pln=50_000)
    )

    forecast = await get_cashflow_forecast(db_session, user_id, today=date(2026, 8, 14))

    assert forecast.budgets.total_budget_pln == 150_000
    assert forecast.budgets.total_spent_pln == 0
    assert forecast.budgets.remaining_pln == 150_000


@pytest.mark.integration
@pytest.mark.asyncio
async def test_forecast_budget_summary_is_zero_without_budgets(db_session) -> None:
    user_id = uuid.uuid4()

    forecast = await get_cashflow_forecast(db_session, user_id, today=date(2026, 8, 14))

    assert forecast.budgets.total_budget_pln == 0
    assert forecast.budgets.total_spent_pln == 0
    assert forecast.budgets.remaining_pln == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_forecast_does_not_return_occurrences_outside_its_horizon(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(
        db_session,
        user_id,
        AccountCreate(name="Konto", type="checking"),
    )
    category = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Czynsz", type="expense"),
    )
    await create_scheduled_item(
        db_session,
        user_id,
        scheduled_item_data(account.id, category.id, due_day=28),
    )

    forecast = await get_cashflow_forecast(db_session, user_id, today=date(2026, 8, 27))

    assert [suggestion.due_date for suggestion in forecast.suggestions] == [date(2026, 8, 28)]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_scheduled_item_returns_false_without_deleting_another_users_item(
    db_session,
) -> None:
    owner_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    account = await create_account(
        db_session, owner_id, AccountCreate(name="Konto", type="checking")
    )
    category = await create_category(
        db_session, owner_id, CategoryCreate(name="Czynsz", type="expense")
    )
    item = await create_scheduled_item(
        db_session, owner_id, scheduled_item_data(account.id, category.id)
    )

    assert await delete_scheduled_item(db_session, other_user_id, item.id) is False
    assert await delete_scheduled_item(db_session, owner_id, uuid.uuid4()) is False
    assert [scheduled.id for scheduled in await get_scheduled_items(db_session, owner_id)] == [
        item.id
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_confirming_due_expense_creates_balanced_scheduled_transaction(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(
        db_session, user_id, AccountCreate(name="Konto", type="checking")
    )
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Czynsz", type="expense")
    )
    item = await create_scheduled_item(
        db_session,
        user_id,
        scheduled_item_data(account.id, category.id, due_day=14, fixed_amount_pln=4_000),
    )

    transaction = await confirm_scheduled_item(
        db_session, user_id, item.id, today=date(2026, 8, 14)
    )

    assert transaction is not None
    assert transaction.source == "scheduled_confirmation"
    assert transaction.type == "expense"
    assert transaction.date == date(2026, 8, 14)
    assert len(transaction.postings) == 2
    assert all(posting.source_amount == 4_000 for posting in transaction.postings)
    assert all(posting.base_amount_pln == 4_000 for posting in transaction.postings)
    assert (
        sum(
            posting.base_amount_pln if posting.direction == "debit" else -posting.base_amount_pln
            for posting in transaction.postings
        )
        == 0
    )
    assert {
        (posting.account_id, posting.category_id, posting.direction)
        for posting in transaction.postings
    } == {
        (account.id, None, "debit"),
        (None, category.id, "credit"),
    }
    assert await row_count(db_session, FinancialTransaction) == 1

    with pytest.raises(ValueError, match="matched_actual"):
        await confirm_scheduled_item(db_session, user_id, item.id, today=date(2026, 8, 14))

    assert await row_count(db_session, FinancialTransaction) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_confirming_due_income_creates_balanced_scheduled_transaction(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(
        db_session, user_id, AccountCreate(name="Konto", type="checking")
    )
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Wynagrodzenie", type="income")
    )
    item = await create_scheduled_item(
        db_session,
        user_id,
        scheduled_item_data(
            account.id,
            category.id,
            name="Wynagrodzenie",
            type="income",
            due_day=14,
            fixed_amount_pln=10_000,
        ),
    )

    transaction = await confirm_scheduled_item(
        db_session, user_id, item.id, today=date(2026, 8, 14)
    )

    assert transaction is not None
    assert transaction.type == "income"
    assert {
        (posting.account_id, posting.category_id, posting.direction)
        for posting in transaction.postings
    } == {
        (account.id, None, "credit"),
        (None, category.id, "debit"),
    }
    assert (
        sum(
            posting.base_amount_pln if posting.direction == "debit" else -posting.base_amount_pln
            for posting in transaction.postings
        )
        == 0
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_confirming_non_pln_scheduled_item_rejects_unresolved_fx(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(
        db_session, user_id, AccountCreate(name="Konto EUR", type="checking", currency="EUR")
    )
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Czynsz", type="expense")
    )
    item = await create_scheduled_item(
        db_session,
        user_id,
        scheduled_item_data(account.id, category.id, currency="EUR", due_day=14),
    )

    with pytest.raises(ValueError, match="PLN"):
        await confirm_scheduled_item(db_session, user_id, item.id, today=date(2026, 8, 14))

    assert await row_count(db_session, FinancialTransaction) == 0
    assert await row_count(db_session, Posting) == 0


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("attribute", ["is_active", "is_budget_account"])
async def test_confirmation_revalidates_changed_budget_account(db_session, attribute: str) -> None:
    user_id = uuid.uuid4()
    account = await create_account(
        db_session, user_id, AccountCreate(name="Konto", type="checking")
    )
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Czynsz", type="expense")
    )
    item = await create_scheduled_item(
        db_session, user_id, scheduled_item_data(account.id, category.id, due_day=14)
    )
    setattr(account, attribute, False)
    await db_session.flush()

    with pytest.raises(ValueError, match="active budget account"):
        await confirm_scheduled_item(db_session, user_id, item.id, today=date(2026, 8, 14))

    assert await row_count(db_session, FinancialTransaction) == 0
    assert await row_count(db_session, Posting) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_confirmation_revalidates_changed_category_type(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(
        db_session, user_id, AccountCreate(name="Konto", type="checking")
    )
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Czynsz", type="expense")
    )
    item = await create_scheduled_item(
        db_session, user_id, scheduled_item_data(account.id, category.id, due_day=14)
    )
    category.type = "income"
    await db_session.flush()

    with pytest.raises(ValueError, match="category type"):
        await confirm_scheduled_item(db_session, user_id, item.id, today=date(2026, 8, 14))

    assert await row_count(db_session, FinancialTransaction) == 0
    assert await row_count(db_session, Posting) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_confirmations_create_exactly_one_transaction(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(
        db_session, user_id, AccountCreate(name="Konto", type="checking")
    )
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Czynsz", type="expense")
    )
    item = await create_scheduled_item(
        db_session, user_id, scheduled_item_data(account.id, category.id, due_day=14)
    )
    await db_session.commit()

    assert db_session.bind is not None
    session_factory = async_sessionmaker(
        db_session.bind, class_=AsyncSession, expire_on_commit=False
    )

    async def confirm_in_separate_transaction() -> FinancialTransaction | ValueError:
        async with session_factory() as session:
            try:
                transaction = await confirm_scheduled_item(
                    session, user_id, item.id, today=date(2026, 8, 14)
                )
                assert transaction is not None
                await session.commit()
                return transaction
            except ValueError as error:
                await session.rollback()
                return error

    results = await asyncio.wait_for(
        asyncio.gather(confirm_in_separate_transaction(), confirm_in_separate_transaction()),
        timeout=5,
    )

    assert sum(isinstance(result, FinancialTransaction) for result in results) == 1
    assert sum(isinstance(result, ValueError) for result in results) == 1
    transactions = list(
        (
            await db_session.execute(
                select(FinancialTransaction).where(
                    FinancialTransaction.user_id == user_id,
                    FinancialTransaction.source == "scheduled_confirmation",
                )
            )
        ).scalars()
    )
    assert len(transactions) == 1
    postings = list(
        (
            await db_session.execute(
                select(Posting).where(Posting.transaction_id == transactions[0].id)
            )
        ).scalars()
    )
    assert len(postings) == 2
    assert (
        sum(
            posting.base_amount_pln if posting.direction == "debit" else -posting.base_amount_pln
            for posting in postings
        )
        == 0
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_confirm_scheduled_item_rejects_missing_foreign_and_unconfirmable_suggestions(
    db_session,
) -> None:
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    account = await create_account(
        db_session, user_id, AccountCreate(name="Konto", type="checking")
    )
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Czynsz", type="expense")
    )
    future = await create_scheduled_item(
        db_session, user_id, scheduled_item_data(account.id, category.id, due_day=15)
    )
    uncertain = await create_scheduled_item(
        db_session,
        user_id,
        scheduled_item_data(account.id, category.id, name="Prąd", due_day=10),
    )
    unknown = await create_scheduled_item(
        db_session,
        user_id,
        scheduled_item_data(
            account.id,
            category.id,
            name="Telefon",
            due_day=14,
            amount_method="last_actual",
            fixed_amount_pln=None,
        ),
    )

    assert (
        await confirm_scheduled_item(db_session, other_user_id, future.id, today=date(2026, 8, 14))
        is None
    )
    assert (
        await confirm_scheduled_item(db_session, user_id, uuid.uuid4(), today=date(2026, 8, 14))
        is None
    )
    for item in (future, uncertain, unknown):
        with pytest.raises(ValueError):
            await confirm_scheduled_item(db_session, user_id, item.id, today=date(2026, 8, 14))

    assert await row_count(db_session, FinancialTransaction) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cashflow_api_deletes_only_the_current_users_scheduled_item(db_session) -> None:
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    account = await create_account(
        db_session, user_id, AccountCreate(name="Konto", type="checking")
    )
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Czynsz", type="expense")
    )
    item = await create_scheduled_item(
        db_session, user_id, scheduled_item_data(account.id, category.id)
    )
    other_account = await create_account(
        db_session, other_user_id, AccountCreate(name="Inne konto", type="checking")
    )
    other_category = await create_category(
        db_session, other_user_id, CategoryCreate(name="Inny czynsz", type="expense")
    )
    other_item = await create_scheduled_item(
        db_session, other_user_id, scheduled_item_data(other_account.id, other_category.id)
    )

    async def override_current_user():
        return SimpleNamespace(id=user_id)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            deleted = await client.delete(f"/api/finance/cashflow/items/{item.id}")
            foreign = await client.delete(f"/api/finance/cashflow/items/{other_item.id}")
            missing = await client.delete(f"/api/finance/cashflow/items/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert deleted.status_code == 204
    assert foreign.status_code == 404
    assert missing.status_code == 404
    assert [scheduled.id for scheduled in await get_scheduled_items(db_session, other_user_id)] == [
        other_item.id
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cashflow_api_confirms_due_item_once(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(
        db_session, user_id, AccountCreate(name="Konto", type="checking")
    )
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Czynsz", type="expense")
    )
    item = await create_scheduled_item(
        db_session,
        user_id,
        scheduled_item_data(
            account.id, category.id, due_day=datetime.now(UTC).astimezone().date().day
        ),
    )

    async def override_current_user():
        return SimpleNamespace(id=user_id)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            confirmed = await client.post(f"/api/finance/cashflow/items/{item.id}/confirm")
            repeated = await client.post(f"/api/finance/cashflow/items/{item.id}/confirm")
    finally:
        app.dependency_overrides.clear()

    assert confirmed.status_code == 200
    assert confirmed.json()["transaction"]["source"] == "scheduled_confirmation"
    assert repeated.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cashflow_api_rejects_unconfirmable_or_inaccessible_items(
    db_session, monkeypatch
) -> None:
    today = date(2026, 8, 14)
    monkeypatch.setattr(finance_service, "_local_today", lambda: today)
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    account = await create_account(
        db_session, user_id, AccountCreate(name="Konto", type="checking")
    )
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Czynsz", type="expense")
    )
    future = await create_scheduled_item(
        db_session, user_id, scheduled_item_data(account.id, category.id, due_day=15)
    )
    uncertain = await create_scheduled_item(
        db_session,
        user_id,
        scheduled_item_data(account.id, category.id, name="Prąd", due_day=10),
    )
    unknown = await create_scheduled_item(
        db_session,
        user_id,
        scheduled_item_data(
            account.id,
            category.id,
            name="Telefon",
            due_day=14,
            amount_method="last_actual",
            fixed_amount_pln=None,
        ),
    )
    other_account = await create_account(
        db_session, other_user_id, AccountCreate(name="Inne konto", type="checking")
    )
    other_category = await create_category(
        db_session, other_user_id, CategoryCreate(name="Inny czynsz", type="expense")
    )
    foreign = await create_scheduled_item(
        db_session,
        other_user_id,
        scheduled_item_data(other_account.id, other_category.id, due_day=14),
    )

    async def override_current_user():
        return SimpleNamespace(id=user_id)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            missing_response = await client.post(
                f"/api/finance/cashflow/items/{uuid.uuid4()}/confirm"
            )
            foreign_response = await client.post(
                f"/api/finance/cashflow/items/{foreign.id}/confirm"
            )
            future_response = await client.post(f"/api/finance/cashflow/items/{future.id}/confirm")
            uncertain_response = await client.post(
                f"/api/finance/cashflow/items/{uncertain.id}/confirm"
            )
            unknown_response = await client.post(
                f"/api/finance/cashflow/items/{unknown.id}/confirm"
            )
    finally:
        app.dependency_overrides.clear()

    assert missing_response.status_code == 404
    assert foreign_response.status_code == 404
    assert future_response.status_code == 422
    assert uncertain_response.status_code == 422
    assert unknown_response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cashflow_api_exposes_settings_items_and_forecast(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(
        db_session,
        user_id,
        AccountCreate(name="Konto", type="checking"),
    )
    category = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Czynsz", type="expense"),
    )

    async def override_current_user():
        return SimpleNamespace(id=user_id)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            settings = await client.patch(
                "/api/finance/cashflow/settings",
                json={"payday_day": 15, "payday_account_id": str(account.id)},
            )
            item = await client.post(
                "/api/finance/cashflow/items",
                json={
                    "name": "Czynsz",
                    "type": "expense",
                    "account_id": str(account.id),
                    "category_id": str(category.id),
                    "currency": "PLN",
                    "due_day": 5,
                    "amount_method": "fixed",
                    "fixed_amount_pln": 4_000,
                },
            )
            forecast = await client.get("/api/finance/cashflow/forecast")
    finally:
        app.dependency_overrides.clear()

    assert settings.status_code == 200
    assert settings.json()["payday_day"] == 15
    assert item.status_code == 201
    assert item.json()["cadence"] == "monthly"
    assert forecast.status_code == 200
    assert forecast.json()["suggestions"][0]["name"] == "Czynsz"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selected_reporting_month_excludes_future_transactions(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(
        db_session,
        user_id,
        AccountCreate(name="Konto", type="checking"),
    )
    income_category = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Wynagrodzenie", type="income"),
    )
    expense_category = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Zakupy", type="expense"),
    )
    await create_income(
        db_session,
        user_id,
        account.id,
        income_category.id,
        10_000,
        date(2026, 8, 10),
    )
    await create_expense(
        db_session,
        user_id,
        account.id,
        expense_category.id,
        2_500,
        date(2026, 8, 12),
    )
    await create_income(
        db_session,
        user_id,
        account.id,
        income_category.id,
        20_000,
        date(2026, 9, 1),
    )
    await create_expense(
        db_session,
        user_id,
        account.id,
        expense_category.id,
        5_000,
        date(2026, 9, 2),
    )

    async def override_current_user():
        return SimpleNamespace(id=user_id)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            summary = await client.get("/api/finance/summary?month=8&year=2026")
            category_summary = await client.get("/api/finance/category-summary?month=8&year=2026")
    finally:
        app.dependency_overrides.clear()

    assert summary.status_code == 200
    assert summary.json()["income_total_pln"] == 10_000
    assert summary.json()["expense_total_pln"] == 2_500
    assert summary.json()["month"] == 8
    assert category_summary.status_code == 200
    assert category_summary.json()["month"] == 8
    assert category_summary.json()["categories"] == [
        {
            "category_id": str(expense_category.id),
            "name": "Zakupy",
            "parent_id": None,
            "total_pln": 2_500,
        }
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_category_summary_uses_selected_reporting_month(db_session) -> None:
    user_id = uuid.uuid4()
    account = await create_account(
        db_session,
        user_id,
        AccountCreate(name="Konto", type="checking"),
    )
    july_category = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Lipiec", type="expense"),
    )
    august_category = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Sierpień", type="expense"),
    )
    await create_expense(
        db_session,
        user_id,
        account.id,
        july_category.id,
        2_500,
        date(2025, 7, 15),
    )
    await create_expense(
        db_session,
        user_id,
        account.id,
        august_category.id,
        5_000,
        date(2025, 8, 1),
    )

    async def override_current_user():
        return SimpleNamespace(id=user_id)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            category_summary = await client.get("/api/finance/category-summary?month=7&year=2025")
    finally:
        app.dependency_overrides.clear()

    assert category_summary.status_code == 200
    assert category_summary.json()["month"] == 7
    assert category_summary.json()["year"] == 2025
    assert category_summary.json()["categories"] == [
        {
            "category_id": str(july_category.id),
            "name": "Lipiec",
            "parent_id": None,
            "total_pln": 2_500,
        }
    ]


async def create_income(
    db_session, user_id, account_id, category_id, amount: int, transaction_date: date | None = None
) -> None:
    await create_transaction(
        db_session,
        user_id,
        TransactionCreate(
            transaction_date=transaction_date,
            description="Wpływ",
            type="income",
            postings=[
                PostingCreate(
                    account_id=account_id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="credit",
                ),
                PostingCreate(
                    category_id=category_id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="debit",
                ),
            ],
        ),
    )


async def create_expense(
    db_session, user_id, account_id, category_id, amount: int, transaction_date: date
) -> None:
    await create_transaction(
        db_session,
        user_id,
        TransactionCreate(
            transaction_date=transaction_date,
            description="Wydatek",
            type="expense",
            postings=[
                PostingCreate(
                    account_id=account_id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=category_id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="credit",
                ),
            ],
        ),
    )


async def row_count(db_session, model) -> int:
    result = await db_session.execute(select(func.count()).select_from(model))
    return result.scalar_one()
