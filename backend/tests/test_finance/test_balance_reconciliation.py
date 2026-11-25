"""Statement balance comparisons use booked history and owner-scoped accounts."""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.schemas import AccountCreate, PostingCreate, TransactionCreate
from app.finance.service import create_account, create_transaction
from tests.test_finance.test_account_currency import add_history, client_for
from tests.test_finance.test_bill_payments import create_owner

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_statement_balance_uses_booked_history_and_owner_scope(
    db_session: AsyncSession,
) -> None:
    owner = await create_owner(db_session)
    other = await create_owner(db_session)
    account = await create_account(db_session, owner, AccountCreate(name="Test", type="checking"))
    booked = await add_history(db_session, owner, account)
    booked.date = date(2026, 1, 10)
    category_id = next(p.category_id for p in booked.postings if p.category_id is not None)
    account_id = account.id
    await create_transaction(
        db_session,
        owner,
        TransactionCreate(
            transaction_date=date(2026, 1, 10),
            description="Pending",
            type="expense",
            is_pending=True,
            postings=[
                PostingCreate(account_id=account_id, source_amount=50, base_amount_pln=50, direction="debit"),
                PostingCreate(category_id=category_id, source_amount=50, base_amount_pln=50, direction="credit"),
            ],
        ),
    )
    await db_session.commit()
    path = f"/api/finance/accounts/{account_id}/balance-reconciliation"
    async with client_for(db_session, owner) as client:
        before = await client.post(path, json={"day": "2026-01-09", "statement_minor": "0"})
        assert before.status_code == 200
        assert before.json()["ledger_minor"] == "0"
        comparison = await client.post(path, json={"day": "2026-01-10", "statement_minor": "-125"})
        assert comparison.status_code == 200
        assert comparison.json() == {
            "day": "2026-01-10",
            "currency": "PLN",
            "ledger_minor": "-100",
            "statement_minor": "-125",
            "difference_minor": "-25",
        }
    async with client_for(db_session, other) as client:
        assert (await client.post(path, json={"day": "2026-01-10", "statement_minor": "0"})).status_code == 404
