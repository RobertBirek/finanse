from datetime import date
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from app.finance.balance_reconciliation import balance_on_day_statement, compare_balances
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bill_payments import create_owner
from tests.test_finance.test_transaction_dates import BOOKING, PURCHASE, explicit
from tests.test_finance.test_transaction_search import seed


def test_balance_comparison_is_exact_and_signed() -> None:
    assert compare_balances(2**53 + 1, 2**53 + 4) == 3
    assert compare_balances(-125, -150) == -25


def test_statement_uses_booked_native_postings_and_checks_ownership() -> None:
    statement = balance_on_day_statement(UUID(int=1), UUID(int=2), date(2026, 1, 2))
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "postings.source_amount" in sql
    assert "financial_transactions.date <=" in sql
    assert "financial_transactions.is_pending IS false" in sql
    assert "financial_transactions.user_id" in sql
    assert "accounts.user_id" in sql


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reconciliation_uses_booking_cutoff_and_does_not_change_ledger(db_session):
    owner = await create_owner(db_session)
    _, _, account, _ = await explicit(db_session, owner)
    url = f"/api/finance/accounts/{account.id}/balance-reconciliation"
    async with client_for(db_session, owner) as client:
        early = await client.post(url, json={"day": PURCHASE.isoformat(), "statement_minor": "0"})
        booked = await client.post(
            url, json={"day": BOOKING.isoformat(), "statement_minor": "-19999"}
        )
        repeat = await client.post(
            url, json={"day": BOOKING.isoformat(), "statement_minor": "-19999"}
        )
    assert early.status_code == booked.status_code == repeat.status_code == 200
    assert early.json()["ledger_minor"] == "0"
    assert booked.json()["ledger_minor"] == "-20000"
    assert booked.json()["difference_minor"] == "1"
    assert repeat.json() == booked.json()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reconciliation_is_owner_scoped_and_ignores_pending_foreign_postings(db_session):
    owner = await create_owner(db_session)
    other = UUID(int=221)
    posted, account, _ = await seed(db_session, owner, amount=1200, currency="EUR", day=BOOKING)
    url = f"/api/finance/accounts/{account.id}/balance-reconciliation"
    payload = {"day": BOOKING.isoformat(), "statement_minor": "-1200"}
    async with client_for(db_session, other) as client:
        assert (await client.post(url, json=payload)).status_code == 404
    async with client_for(db_session, owner) as client:
        booked = await client.post(url, json=payload)
        posted.is_pending = True
        await db_session.flush()
        pending = await client.post(url, json=payload)
    assert booked.status_code == pending.status_code == 200
    assert booked.json()["currency"] == "EUR"
    assert booked.json()["ledger_minor"] == "-1200"
    assert pending.json()["ledger_minor"] == "0"
