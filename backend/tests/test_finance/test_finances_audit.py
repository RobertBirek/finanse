import asyncio
from collections.abc import AsyncIterator
from datetime import date
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import get_db
from app.finance.cashflow import ScheduleConfirmationConflict
from app.finance.imports.models import ImportBatch
from app.finance.manual_refunds import create_manual_expense_refund
from app.finance.models import FinancialTransaction
from app.finance.schemas import (
    AccountCreate,
    CategoryCreate,
    ExpenseRefundCreate,
    ScheduledFinanceConfirmationRequest,
)
from app.finance.service import (
    confirm_scheduled_item,
    create_account,
    create_category,
    create_scheduled_item,
    get_cashflow_forecast,
)
from app.identity.router import get_current_user
from app.main import app
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bill_payments import create_owner
from tests.test_finance.test_cashflow import create_expense, scheduled_item_data

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_month_boundary_refund_and_ambiguous_payment(db_session: AsyncSession) -> None:
    owner = await create_owner(db_session)
    account = await create_account(db_session, owner, AccountCreate(name="Konto", type="checking"))
    category = await create_category(
        db_session, owner, CategoryCreate(name="Czynsz", type="expense")
    )
    item = await create_scheduled_item(
        db_session, owner, scheduled_item_data(account.id, category.id, due_day=28)
    )
    today = date(2026, 3, 1)
    due_date = date(2026, 2, 28)
    await create_manual_expense_refund(
        db_session,
        owner,
        ExpenseRefundCreate(
            account_id=account.id,
            category_id=category.id,
            amount_minor=4000,
            description="Zwrot",
            transaction_date=today,
        ),
    )
    forecast = await get_cashflow_forecast(db_session, owner, today=today)
    occurrence = next(row for row in forecast.suggestions if row.due_date == due_date)
    assert occurrence.status == "overdue"
    assert occurrence.included_in_forecast
    assert occurrence.actual_transaction_id is None

    with pytest.raises(ScheduleConfirmationConflict):
        await confirm_scheduled_item(
            db_session,
            owner,
            item.id,
            today=today,
            expected=ScheduledFinanceConfirmationRequest(due_date=due_date, expected_amount_pln=1),
        )
    await create_expense(db_session, owner, account.id, category.id, 4000, date(2026, 2, 25))
    forecast = await get_cashflow_forecast(db_session, owner, today=today)
    occurrence = next(row for row in forecast.suggestions if row.due_date == due_date)
    assert occurrence.status == "matched_actual"
    await create_scheduled_item(
        db_session,
        owner,
        scheduled_item_data(account.id, category.id, name="Drugi czynsz", due_day=28),
    )
    forecast = await get_cashflow_forecast(db_session, owner, today=today)
    occurrences = [row for row in forecast.suggestions if row.due_date == due_date]
    assert len(occurrences) == 2
    assert all(
        row.status == "match_uncertain" and not row.actual_transaction_id for row in occurrences
    )
    assert forecast.safe_daily_limit_pln is None


async def test_manual_write_replays_atomically_and_keeps_category_amounts(
    db_session: AsyncSession,
) -> None:
    owner = await create_owner(db_session)
    account = await create_account(db_session, owner, AccountCreate(name="Konto", type="checking"))
    root = await create_category(
        db_session, owner, CategoryCreate(name="Mieszkanie", type="expense")
    )
    category = await create_category(
        db_session, owner, CategoryCreate(name="Czynsz", type="expense", parent_id=root.id)
    )
    other = await create_category(db_session, owner, CategoryCreate(name="Naprawa", type="expense"))
    second = await create_account(
        db_session, owner, AccountCreate(name="Oszczędności", type="savings")
    )
    euro = await create_account(
        db_session, owner, AccountCreate(name="EUR", type="checking", currency="EUR")
    )
    await db_session.commit()
    assert db_session.bind is not None
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def database() -> AsyncIterator[AsyncSession]:
        async with factory() as session, session.begin():
            yield session

    payload = {
        "description": "Wspólny rachunek",
        "type": "expense",
        "booking_date": "2026-11-01",
        "purchase_date": "2026-10-31",
        "postings": [
            {
                "account_id": str(account.id),
                "source_amount": 10000,
                "base_amount_pln": 10000,
                "direction": "debit",
            },
            {
                "category_id": str(category.id),
                "source_amount": 2000,
                "base_amount_pln": 2000,
                "direction": "credit",
            },
            {
                "category_id": str(other.id),
                "source_amount": 8000,
                "base_amount_pln": 8000,
                "direction": "credit",
            },
        ],
    }
    path = "/api/finance/transactions"
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=owner)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"Idempotency-Key": "the-same-confirmation"}
            first, retry = await asyncio.gather(
                client.post(path, json=payload, headers=headers),
                client.post(path, json=payload, headers=headers),
            )
            assert first.status_code == retry.status_code == 201
            assert first.json() == retry.json()
            assert len(first.json()["postings"]) == 3
            changed = await client.post(
                path, json={**payload, "description": "Druga"}, headers=headers
            )
            assert changed.status_code == 409
            refund = {
                "account_id": str(account.id),
                "category_id": str(category.id),
                "amount_minor": 500,
                "transaction_date": "2026-10-31",
                "description": "Zwrot części kwoty",
            }
            for _ in range(2):
                result = await client.post(path + "/expense-refund", json=refund, headers=headers)
                assert result.status_code == 201
            transfer = {
                "type": "transfer",
                "transaction_date": "2026-10-31",
                "description": "Między własnymi kontami",
                "postings": [
                    {
                        "account_id": str(account.id),
                        "source_amount": 3000,
                        "base_amount_pln": 3000,
                        "direction": "debit",
                    },
                    {
                        "account_id": str(second.id),
                        "source_amount": 3000,
                        "base_amount_pln": 3000,
                        "direction": "credit",
                    },
                ],
            }
            exchange = {
                "from_account_id": str(account.id),
                "to_account_id": str(euro.id),
                "from_amount": 4000,
                "fx_rate": 4,
                "transaction_date": "2026-10-31",
                "description": "Wymiana na EUR",
            }
            for endpoint, data in [(path, transfer), (path + "/exchange", exchange)]:
                money_movement = await client.post(
                    endpoint, json=data, headers={"Idempotency-Key": "move"}
                )
                retry = await client.post(endpoint, json=data, headers={"Idempotency-Key": "move"})
                assert money_movement.status_code == retry.status_code == 201
                assert money_movement.json() == retry.json()
                assert (
                    sum(
                        posting["base_amount_pln"] * (1 if posting["direction"] == "credit" else -1)
                        for posting in retry.json()["postings"]
                    )
                    == 0
                )
            summary = await client.get("/api/finance/summary", params={"month": 10, "year": 2026})
            assert summary.status_code == 200
            assert summary.json()["income_total_pln"] == 0
            assert summary.json()["expense_total_pln"] == 9500
            search = await client.get(
                path + "/search",
                params={
                    "category_id": str(root.id),
                    "include_descendants": "true",
                    "budget_accounts_only": "true",
                    "date_basis": "purchase",
                    "date_from": "2026-10-01",
                    "date_to": "2026-10-31",
                },
            )
            assert search.status_code == 200
            assert sorted(row["matched_category_amount_pln"] for row in search.json()["items"]) == [
                -500,
                2000,
            ]
    finally:
        app.dependency_overrides.clear()
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(FinancialTransaction)
            .where(FinancialTransaction.user_id == owner)
        )
        == 4
    )


async def test_import_history_filters_before_paging_and_is_owner_scoped(
    db_session: AsyncSession,
) -> None:
    owner = await create_owner(db_session)
    other = await create_owner(db_session)
    db_session.add_all(
        [ImportBatch(user_id=owner, kind="statement") for _ in range(26)]
        + [ImportBatch(user_id=owner, kind="loan_schedule") for _ in range(51)]
        + [ImportBatch(user_id=other, kind="statement")]
    )
    await db_session.flush()
    async with client_for(db_session, owner) as client:
        first = await client.get("/api/finance/imports/history", params={"kind": "statement"})
        last = await client.get(
            "/api/finance/imports/history", params={"kind": "statement", "offset": 25}
        )
        schedules = await client.get(
            "/api/finance/imports/history", params={"kind": "loan_schedule"}
        )
        assert first.status_code == last.status_code == schedules.status_code == 200
        assert first.json()["total"] == last.json()["total"] == 26
        assert len(first.json()["items"]) == 25
        assert len(last.json()["items"]) == 1
        assert schedules.json()["total"] == 51
        assert last.json()["items"][0]["id"] not in {row["id"] for row in first.json()["items"]}
