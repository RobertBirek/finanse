"""Read-only search over the complete owned ledger, never a truncated client list."""

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.finance import service
from app.finance.schemas import (
    AccountCreate,
    CategoryCreate,
    PostingCreate,
    TransactionCreate,
    TransactionSearch,
)
from app.identity.router import get_current_user
from app.main import app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def seed(
    db, user, description="Zakupy", amount=12345, currency="PLN", day=date(2026, 10, 20)
):
    account = await service.create_account(
        db,
        user,
        AccountCreate(
            name="Portfel " + currency,
            type="checking",
            currency=currency,
        ),
    )
    category = await service.create_category(
        db, user, CategoryCreate(name="Jedzenie", type="expense")
    )
    rate = 1 if currency == "PLN" else 4
    txn = await service.create_transaction(
        db,
        user,
        TransactionCreate(
            transaction_date=day,
            description=description,
            type="expense",
            postings=[
                PostingCreate(
                    account_id=account.id,
                    source_amount=amount,
                    source_currency=currency,
                    base_amount_pln=amount * rate,
                    fx_rate=rate,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=category.id,
                    source_amount=amount,
                    source_currency=currency,
                    base_amount_pln=amount * rate,
                    fx_rate=rate,
                    direction="credit",
                ),
            ],
        ),
    )
    return txn, account, category


async def test_search_is_owned_case_insensitive_and_spans_account_category_description(db_session):
    owner, other = uuid.uuid4(), uuid.uuid4()
    txn, account, category = await seed(db_session, owner, "Kawa 100%_ / specjalna")
    await seed(db_session, other, "Kawa 100%_ / specjalna")
    for text in ["KAWA", "portfel", "jedzenie", "%_ /", "  kawa  "]:
        page = await service.search_transactions(db_session, owner, TransactionSearch(q=text))
        assert page.total == 1
        assert [x.id for x in page.items] == [txn.id]
    for filters in [
        TransactionSearch(q="' OR 1=1 --"),
        TransactionSearch(account_id=uuid.uuid4()),
        TransactionSearch(category_id=uuid.uuid4()),
        TransactionSearch(q="missing"),
    ]:
        assert (await service.search_transactions(db_session, owner, filters)).total == 0
    # Archived entities remain searchable in historical records.
    account.is_active = False
    category.is_active = False
    await db_session.flush()
    assert (
        await service.search_transactions(
            db_session,
            owner,
            TransactionSearch(
                account_id=account.id,
                category_id=category.id,
            ),
        )
    ).total == 1


async def test_inclusive_dates_and_amounts_are_pln_not_source_units(db_session):
    owner = uuid.uuid4()
    txn, account, category = await seed(db_session, owner, currency="EUR", amount=1000)
    await seed(db_session, owner, amount=4000, day=date(2026, 10, 19))
    filters = TransactionSearch(
        date_from=date(2026, 10, 20),
        date_to=date(2026, 10, 20),
        currency="EUR",
        min_amount_pln=4000,
        max_amount_pln=4000,
        category_id=category.id,
        account_id=account.id,
        type="expense",
    )
    page = await service.search_transactions(db_session, owner, filters)
    assert page.total == 1 and page.items[0].id == txn.id
    assert (
        await service.search_transactions(
            db_session,
            owner,
            TransactionSearch(
                currency="EUR",
                max_amount_pln=1000,
            ),
        )
    ).total == 0


async def test_currency_and_amount_must_match_the_selected_account_leg(db_session):
    user = uuid.uuid4()
    eur = await service.create_account(
        db_session, user, AccountCreate(name="Euro", type="checking", currency="EUR")
    )
    pln = await service.create_account(
        db_session, user, AccountCreate(name="Złote", type="checking")
    )
    txn = await service.create_transaction(
        db_session,
        user,
        TransactionCreate(
            transaction_date=date(2026, 10, 20),
            description="Wymiana",
            type="exchange",
            postings=[
                PostingCreate(
                    account_id=eur.id,
                    source_currency="EUR",
                    source_amount=1000,
                    base_amount_pln=4000,
                    fx_rate=4,
                    direction="debit",
                ),
                PostingCreate(
                    account_id=pln.id,
                    source_currency="PLN",
                    source_amount=4000,
                    base_amount_pln=4000,
                    fx_rate=1,
                    direction="credit",
                ),
            ],
        ),
    )
    all_items = await service.search_transactions(db_session, user, TransactionSearch())
    assert all_items.total == 1 and all_items.items[0].id == txn.id
    assert (
        await service.search_transactions(
            db_session,
            user,
            TransactionSearch(
                account_id=pln.id,
                currency="EUR",
            ),
        )
    ).total == 0


async def test_pagination_beyond_fifty_and_tie_breaking_without_duplicates(db_session):
    user = uuid.uuid4()
    for i in range(53):
        txn, _, _ = await seed(db_session, user, description=f"Zakup {i}")
        txn.created_at = datetime(2026, 10, 20, tzinfo=UTC)
    await db_session.flush()
    pages = [
        await service.search_transactions(db_session, user, TransactionSearch(limit=25, offset=o))
        for o in [0, 25, 50, 75]
    ]
    assert [len(p.items) for p in pages] == [25, 25, 3, 0]
    assert all(p.total == 53 for p in pages)
    ids = [x.id for p in pages for x in p.items]
    assert len(set(ids)) == 53
    assert ids == sorted(ids, reverse=True)


@pytest.mark.parametrize(
    "params",
    [
        {"date_from": "2026-11-01", "date_to": "2026-01-01"},
        {"min_amount_pln": 100, "max_amount_pln": 1},
        {"min_amount_pln": -1},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"currency": "XYZ"},
        {"q": "x" * 201},
        {"account_id": "not-a-uuid"},
        {"date_from": "2026-02-30"},
    ],
)
async def test_invalid_filters_return_422_not_500(async_client, params):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    response = await async_client.get("/api/finance/transactions/search", params=params)
    assert response.status_code == 422


async def test_search_api_response_contract_and_ownership(async_client, db_session):
    user = uuid.uuid4()
    txn, _, _ = await seed(db_session, user)
    await seed(db_session, uuid.uuid4())
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user)
    response = await async_client.get(
        "/api/finance/transactions/search", params={"q": "zakupy", "limit": 1}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1 and data["limit"] == 1 and data["offset"] == 0
    assert data["items"][0]["id"] == str(txn.id)
    app.dependency_overrides.pop(get_current_user)
    assert (await async_client.get("/api/finance/transactions/search")).status_code == 401
