from datetime import date
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql


def _id(value: int) -> UUID:
    return UUID(int=value)


async def test_net_spending_uses_signed_period_contributions_without_counting_today():
    from app.finance.spending_comparison import get_spending_comparison

    async def projected_rows():
        # One current purchase uses two expense postings; the same transaction
        # must be presented as one contributor.
        for row in [
            (_id(1), date(2026, 10, 23), "Previous", _id(8), "Home", 10000),
            (_id(2), date(2026, 11, 6), "Purchase", _id(8), "Home", 13000),
            (_id(2), date(2026, 11, 6), "Purchase", _id(9), "Other", 5000),
            (_id(3), date(2026, 11, 19), "Refund", _id(8), "Home", -2000),
            (_id(4), date(2026, 11, 20), "Today", _id(8), "Home", 90000),
        ]:
            yield row

    db = AsyncMock()
    db.stream.return_value = projected_rows()
    owner = uuid4()
    result = await get_spending_comparison(db, owner, days=14, today=date(2026, 11, 20))
    assert result.previous_start == date(2026, 10, 23)
    assert result.current_start == date(2026, 11, 6)
    assert result.end_exclusive == date(2026, 11, 20)
    assert (result.previous_total_pln, result.current_total_pln, result.delta_pln) == (
        10000,
        16000,
        6000,
    )
    assert [row.delta_pln for row in result.transactions] == [18000, -10000, -2000]


def test_projection_uses_owned_budget_account_existence_and_purchase_date():
    from app.finance.reporting import spending_postings

    owner = _id(1)
    compiled = spending_postings(owner, date(2026, 10, 24), date(2026, 11, 21)).compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    sql = str(compiled).lower()
    assert "exists (select" in sql and "is_budget_account is true" in sql
    assert "purchase_date" in sql
    assert "2026-10-24" in sql and "2026-11-21" in sql
    assert "'transfer'" not in sql
    assert sql.count(str(owner)) >= 3


@pytest.mark.integration
async def test_postgresql_net_spending_uses_purchase_date_and_counts_each_posting_once(db_session):
    from app.finance.manual_refunds import create_manual_expense_refund
    from app.finance.models import Account, Category, FinancialTransaction, Posting
    from app.finance.schemas import ExpenseRefundCreate
    from app.finance.spending_comparison import get_spending_comparison
    from app.identity.models import User

    user = User(email="comparison@example.test", display_name="Tester", password_hash="unused")
    db_session.add(user)
    await db_session.flush()
    owner, other = user.id, uuid4()
    account = Account(
        user_id=owner, name="Owned", type="checking", currency="PLN", is_budget_account=True
    )
    second = Account(
        user_id=owner, name="Second", type="checking", currency="PLN", is_budget_account=True
    )
    foreign = Account(
        user_id=other, name="Foreign", type="checking", currency="PLN", is_budget_account=True
    )
    category = Category(user_id=owner, name="Home", type="expense")
    db_session.add_all([account, second, foreign, category])
    await db_session.flush()

    async def add(kind, booked, amount, *, purchased=None, accounts=(account,)):
        from app.finance.models import TransactionDateMetadata

        txn = FinancialTransaction(user_id=owner, date=booked, description=kind, type=kind)
        db_session.add(txn)
        await db_session.flush()
        if purchased:
            db_session.add(
                TransactionDateMetadata(
                    user_id=owner,
                    transaction_id=txn.id,
                    purchase_date=purchased,
                    purchase_date_source="manual",
                    booking_date=booked,
                    booking_date_source="manual",
                )
            )
        day_amount = abs(amount)
        rows = [(None, category.id, "credit" if amount > 0 else "debit", day_amount)]
        for index, item in enumerate(accounts):
            part = (
                day_amount // len(accounts)
                if index
                else day_amount - (len(accounts) - 1) * (day_amount // len(accounts))
            )
            rows.append((item.id, None, "debit" if amount > 0 else "credit", part))
        db_session.add_all(
            [
                Posting(
                    transaction_id=txn.id,
                    account_id=account_id,
                    category_id=category_id,
                    direction=direction,
                    source_currency="PLN",
                    source_amount=part,
                    base_amount_pln=part,
                    fx_rate=1,
                    fx_rate_source="manual",
                )
                for account_id, category_id, direction, part in rows
            ]
        )
        await db_session.flush()

    await add("expense", date(2026, 11, 6), 10000)
    await add(
        "expense",
        date(2026, 11, 21),
        18000,
        purchased=date(2026, 11, 7),
        accounts=(account, second),
    )
    await create_manual_expense_refund(
        db_session,
        owner,
        ExpenseRefundCreate(
            account_id=account.id,
            category_id=category.id,
            amount_minor=2000,
            description="Test refund",
            transaction_date=date(2026, 11, 20),
        ),
    )
    await add("transfer", date(2026, 11, 20), 50000)
    await add("expense", date(2026, 11, 20), 70000, accounts=(foreign,))
    result = await get_spending_comparison(db_session, owner, days=14, today=date(2026, 11, 21))
    assert (result.previous_total_pln, result.current_total_pln, result.delta_pln) == (
        10000,
        16000,
        6000,
    )
