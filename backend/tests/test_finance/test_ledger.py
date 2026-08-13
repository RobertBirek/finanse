"""Tests for finance domain — double-entry ledger invariants."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.finance.schemas import AccountCreate, CategoryCreate, PostingCreate, TransactionCreate
from app.finance.service import (
    _validate_posting_sum,
    create_account,
    create_category,
    create_transaction,
    get_category_summary,
    get_financial_summary,
)
from app.identity.router import get_current_user
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
async def test_category_only_posting_is_persisted(db_session):
    user_id = uuid.uuid4()
    account = await create_account(
        db_session, user_id, AccountCreate(name="Konto", type="checking")
    )
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Paliwo", type="expense")
    )

    transaction = await create_transaction(
        db_session,
        user_id,
        TransactionCreate(
            description="Paliwo",
            type="expense",
            postings=[
                PostingCreate(
                    account_id=account.id,
                    category_id=None,
                    source_amount=5000,
                    source_currency="PLN",
                    base_amount_pln=5000,
                    fx_rate=1.0,
                    fx_rate_source="manual",
                    direction="credit",
                    is_budget_impact=True,
                ),
                PostingCreate(
                    account_id=None,
                    category_id=category.id,
                    source_amount=5000,
                    source_currency="PLN",
                    base_amount_pln=5000,
                    fx_rate=1.0,
                    fx_rate_source="manual",
                    direction="debit",
                    is_budget_impact=True,
                ),
            ],
        ),
    )

    assert transaction.postings[0].account_id == account.id
    assert transaction.postings[1].account_id is None


async def create_categorized_transaction(
    db_session,
    user_id,
    account_id,
    category_id,
    *,
    transaction_type="expense",
    amount=10000,
    is_budget_impact=True,
):
    account_direction, category_direction = (
        ("credit", "debit") if transaction_type == "expense" else ("debit", "credit")
    )
    return await create_transaction(
        db_session,
        user_id,
        TransactionCreate(
            transaction_date=datetime.now(UTC).date(),
            description="Skategoryzowana transakcja",
            type=transaction_type,
            postings=[
                PostingCreate(
                    account_id=account_id,
                    source_amount=amount,
                    source_currency="PLN",
                    base_amount_pln=amount,
                    direction=account_direction,
                    is_budget_impact=is_budget_impact,
                ),
                PostingCreate(
                    category_id=category_id,
                    source_amount=amount,
                    source_currency="PLN",
                    base_amount_pln=amount,
                    direction=category_direction,
                    is_budget_impact=is_budget_impact,
                ),
            ],
        ),
    )


async def create_legacy_combined_transaction(
    db_session,
    user_id,
    account_id,
    category_id,
    *,
    transaction_type="expense",
    amount=10000,
):
    account_direction, category_direction = (
        ("credit", "debit") if transaction_type == "expense" else ("debit", "credit")
    )
    return await create_transaction(
        db_session,
        user_id,
        TransactionCreate(
            transaction_date=datetime.now(UTC).date(),
            description="Historyczny posting laczony",
            type=transaction_type,
            postings=[
                PostingCreate(
                    account_id=account_id,
                    source_amount=amount,
                    source_currency="PLN",
                    base_amount_pln=amount,
                    direction=account_direction,
                ),
                PostingCreate(
                    account_id=account_id,
                    category_id=category_id,
                    source_amount=amount,
                    source_currency="PLN",
                    base_amount_pln=amount,
                    direction=category_direction,
                ),
            ],
        ),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_analytics_exclude_legacy_combined_account_category_postings(db_session):
    user_id = uuid.uuid4()
    account = await create_account(db_session, user_id, AccountCreate(name="ING", type="checking"))
    transport = await create_category(
        db_session, user_id, CategoryCreate(name="Transport", type="expense")
    )
    fuel = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Paliwo", type="expense", parent_id=transport.id),
    )
    income_category = await create_category(
        db_session, user_id, CategoryCreate(name="Wyplata", type="income")
    )

    await create_categorized_transaction(db_session, user_id, account.id, fuel.id, amount=5000)
    await create_categorized_transaction(
        db_session,
        user_id,
        account.id,
        income_category.id,
        transaction_type="income",
        amount=4000,
    )
    await create_legacy_combined_transaction(db_session, user_id, account.id, fuel.id, amount=3000)
    await create_legacy_combined_transaction(
        db_session,
        user_id,
        account.id,
        income_category.id,
        transaction_type="income",
        amount=2000,
    )

    financial_summary = await get_financial_summary(db_session, user_id)
    category_summary = await get_category_summary(db_session, user_id)

    assert financial_summary.expense_total_pln == 5000
    assert financial_summary.income_total_pln == 4000
    assert [(category.name, category.total_pln) for category in category_summary.categories] == [
        ("Paliwo", 5000)
    ]
    assert [(group.name, group.total_pln) for group in category_summary.groups] == [
        ("Transport", 5000)
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_summary_excludes_offbudget_accounts_and_category_impact(db_session):
    user_id = uuid.uuid4()
    budget_account = await create_account(
        db_session, user_id, AccountCreate(name="ING", type="checking", is_budget_account=True)
    )
    offbudget_account = await create_account(
        db_session,
        user_id,
        AccountCreate(name="Pozyczka", type="credit", is_budget_account=False),
    )
    expense_category = await create_category(
        db_session, user_id, CategoryCreate(name="Zakupy", type="expense")
    )
    income_category = await create_category(
        db_session, user_id, CategoryCreate(name="Wyplata", type="income")
    )

    await create_categorized_transaction(
        db_session, user_id, budget_account.id, expense_category.id
    )
    await create_categorized_transaction(
        db_session,
        user_id,
        offbudget_account.id,
        expense_category.id,
        amount=10000,
        is_budget_impact=False,
    )
    await create_categorized_transaction(
        db_session,
        user_id,
        budget_account.id,
        income_category.id,
        transaction_type="income",
        amount=4000,
    )

    summary = await get_financial_summary(db_session, user_id)

    assert summary.expense_total_pln == 10000
    assert summary.income_total_pln == 4000
    assert [account["name"] for account in summary.accounts] == ["ING"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_category_summary_aggregates_children_and_excludes_offbudget(db_session):
    user_id = uuid.uuid4()
    budget_account = await create_account(
        db_session, user_id, AccountCreate(name="ING", type="checking", is_budget_account=True)
    )
    offbudget_account = await create_account(
        db_session,
        user_id,
        AccountCreate(name="Pozyczka", type="credit", is_budget_account=False),
    )
    transport = await create_category(
        db_session, user_id, CategoryCreate(name="Transport", type="expense")
    )
    fuel = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Paliwo", type="expense", parent_id=transport.id),
    )

    await create_categorized_transaction(
        db_session, user_id, budget_account.id, fuel.id, amount=5000
    )
    await create_categorized_transaction(
        db_session,
        user_id,
        offbudget_account.id,
        fuel.id,
        amount=3000,
        is_budget_impact=False,
    )

    async def override_current_user():
        return SimpleNamespace(id=user_id)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_db] = override_get_db
    transport_client = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport_client, base_url="http://test") as client:
            response = await client.get("/api/finance/category-summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["categories"] == [
        {
            "category_id": str(fuel.id),
            "name": "Paliwo",
            "parent_id": str(transport.id),
            "total_pln": 5000,
        }
    ]
    assert body["groups"] == [
        {
            "category_id": str(transport.id),
            "name": "Transport",
            "parent_id": None,
            "total_pln": 5000,
        }
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_posting_requires_account_or_category(db_session):
    user_id = uuid.uuid4()

    with pytest.raises(ValueError, match="at least an account or category"):
        await create_transaction(
            db_session,
            user_id,
            TransactionCreate(
                description="Nieprawidlowy posting",
                type="expense",
                postings=[
                    PostingCreate(
                        account_id=None,
                        category_id=None,
                        source_amount=5000,
                        source_currency="PLN",
                        base_amount_pln=5000,
                        fx_rate=1.0,
                        fx_rate_source="manual",
                        direction="credit",
                    ),
                    PostingCreate(
                        account_id=None,
                        category_id=None,
                        source_amount=5000,
                        source_currency="PLN",
                        base_amount_pln=5000,
                        fx_rate=1.0,
                        fx_rate_source="manual",
                        direction="debit",
                    ),
                ],
            ),
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
