import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.database import get_db
from app.finance.models import FinanceSettings, FinancialTransaction, Posting
from app.finance.schemas import (
    AccountCreate,
    CategoryCreate,
    PostingCreate,
    ScheduledFinanceItemCreate,
    TransactionCreate,
)
from app.finance.service import (
    create_account,
    create_category,
    create_scheduled_item,
    create_transaction,
    get_cashflow_forecast,
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
