"""Tests for finance domain — double-entry ledger invariants."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.finance.schemas import AccountCreate, CategoryCreate, PostingCreate, TransactionCreate
from app.finance.service import (
    _validate_posting_sum,
    create_account,
    create_category,
    create_transaction,
)
from app.main import app


class TestDoubleEntryInvariant:
    def test_valid_postings_sum_to_zero(self):
        """Debit and credit both use positive base_amount_pln — signs from direction."""
        acc1 = uuid.uuid4()
        acc2 = uuid.uuid4()
        postings = [
            PostingCreate(
                account_id=acc1,
                source_amount=50000,
                source_currency="PLN",
                base_amount_pln=50000,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="debit",
            ),
            PostingCreate(
                account_id=acc2,
                source_amount=50000,
                source_currency="PLN",
                base_amount_pln=50000,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="credit",
            ),
        ]
        _validate_posting_sum(postings, "expense")

    def test_invalid_postings_non_zero_raises(self):
        acc1 = uuid.uuid4()
        acc2 = uuid.uuid4()
        postings = [
            PostingCreate(
                account_id=acc1,
                source_amount=50000,
                source_currency="PLN",
                base_amount_pln=50000,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="debit",
            ),
            PostingCreate(
                account_id=acc2,
                source_amount=49999,
                source_currency="PLN",
                base_amount_pln=49999,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="credit",
            ),
        ]
        with pytest.raises(ValueError, match="must equal 0"):
            _validate_posting_sum(postings, "expense")

    def test_empty_postings_raises(self):
        with pytest.raises(ValueError, match="at least 2"):
            _validate_posting_sum([], "expense")

    def test_single_posting_raises(self):
        acc1 = uuid.uuid4()
        postings = [
            PostingCreate(
                account_id=acc1,
                source_amount=50000,
                source_currency="PLN",
                base_amount_pln=50000,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="debit",
            ),
        ]
        with pytest.raises(ValueError, match="must equal 0"):
            _validate_posting_sum(postings, "expense")

    def test_transfer_with_fee(self):
        """500 PLN transfer + 1 PLN fee = 3 postings, balanced."""
        acc_source = uuid.uuid4()
        acc_dest = uuid.uuid4()
        acc_fees = uuid.uuid4()
        postings = [
            PostingCreate(
                account_id=acc_source,
                source_amount=50000,
                source_currency="PLN",
                base_amount_pln=50000,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="debit",
            ),
            PostingCreate(
                account_id=acc_dest,
                source_amount=49900,
                source_currency="PLN",
                base_amount_pln=49900,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="credit",
            ),
            PostingCreate(
                account_id=acc_fees,
                source_amount=100,
                source_currency="PLN",
                base_amount_pln=100,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="credit",
            ),
        ]
        _validate_posting_sum(postings, "transfer")

    def test_exchange_pln_to_eur(self):
        """100 EUR * 4.30 = 430 PLN. Debit PLN, credit EUR."""
        acc_pln = uuid.uuid4()
        acc_eur = uuid.uuid4()
        postings = [
            PostingCreate(
                account_id=acc_pln,
                source_amount=430,
                source_currency="PLN",
                base_amount_pln=430,
                fx_rate=4.30,
                fx_rate_source="manual",
                direction="debit",
            ),
            PostingCreate(
                account_id=acc_eur,
                source_amount=100,
                source_currency="EUR",
                base_amount_pln=430,
                fx_rate=4.30,
                fx_rate_source="manual",
                direction="credit",
            ),
        ]
        _validate_posting_sum(postings, "exchange")


class TestFinanceAPI:
    @pytest.mark.asyncio
    async def test_get_accounts_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/finance/accounts")
            assert response.status_code == 401


def transaction_data(account_id, category_id=None, *, currency="PLN", amount=100):
    return TransactionCreate(
        description="Test transaction",
        type="expense",
        postings=[
            PostingCreate(
                account_id=account_id,
                category_id=category_id,
                source_amount=amount,
                source_currency=currency,
                base_amount_pln=amount,
                direction="debit",
            ),
            PostingCreate(
                account_id=account_id,
                category_id=category_id,
                source_amount=amount,
                source_currency=currency,
                base_amount_pln=amount,
                direction="credit",
            ),
        ],
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_transaction_rejects_another_users_account_without_mutating_db(db_session):
    owner_id = uuid.uuid4()
    another_user_id = uuid.uuid4()
    account = await create_account(
        db_session, another_user_id, AccountCreate(name="Private", type="checking")
    )

    with pytest.raises(ValueError, match="Account not found"):
        await create_transaction(db_session, owner_id, transaction_data(account.id))

    assert await _count_transactions(db_session, owner_id) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_transaction_rejects_another_users_category_without_mutating_db(db_session):
    owner_id = uuid.uuid4()
    another_user_id = uuid.uuid4()
    account = await create_account(
        db_session, owner_id, AccountCreate(name="Owned", type="checking")
    )
    category = await create_category(
        db_session, another_user_id, CategoryCreate(name="Private", type="expense")
    )

    with pytest.raises(ValueError, match="Category not found"):
        await create_transaction(db_session, owner_id, transaction_data(account.id, category.id))

    assert await _count_transactions(db_session, owner_id) == 0


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("currency", "amount", "expected_error"),
    [
        ("GBP", 100, "Unsupported currency"),
        ("PLN", 0, "positive"),
        ("PLN", -1, "positive"),
    ],
)
async def test_transaction_rejects_invalid_posting_values_without_mutating_db(
    db_session, currency, amount, expected_error
):
    user_id = uuid.uuid4()
    account = await create_account(
        db_session, user_id, AccountCreate(name="Owned", type="checking")
    )

    with pytest.raises(ValueError, match=expected_error):
        await create_transaction(
            db_session, user_id, transaction_data(account.id, currency=currency, amount=amount)
        )

    assert await _count_transactions(db_session, user_id) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_transaction_rejects_posting_currency_mismatching_account(db_session):
    user_id = uuid.uuid4()
    account = await create_account(
        db_session, user_id, AccountCreate(name="Euro", type="checking", currency="EUR")
    )

    with pytest.raises(ValueError, match="does not match account currency"):
        await create_transaction(db_session, user_id, transaction_data(account.id))

    assert await _count_transactions(db_session, user_id) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_account_rejects_unsupported_currency_without_mutating_db(db_session):
    user_id = uuid.uuid4()

    with pytest.raises(ValueError, match="Unsupported currency"):
        await create_account(
            db_session, user_id, AccountCreate(name="Invalid", type="checking", currency="GBP")
        )

    from sqlalchemy import func, select

    from app.finance.models import Account

    result = await db_session.execute(
        select(func.count()).select_from(Account).where(Account.user_id == user_id)
    )
    assert result.scalar_one() == 0


async def _count_transactions(db_session, user_id):
    from sqlalchemy import func, select

    from app.finance.models import FinancialTransaction

    result = await db_session.execute(
        select(func.count())
        .select_from(FinancialTransaction)
        .where(FinancialTransaction.user_id == user_id)
    )
    return result.scalar_one()
