"""Currency is editable only before any ledger or import/schedule dependency."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import get_db
from app.finance import service
from app.finance.models import (
    Account,
    ActualImportMapping,
    FinancialTransaction,
    Posting,
    ScheduledFinanceItem,
)
from app.finance.schemas import (
    AccountCreate,
    AccountUpdate,
    CategoryCreate,
    PostingCreate,
    ScheduledFinanceItemCreate,
    ScheduledFinanceItemUpdate,
    TransactionCreate,
)
from app.identity.router import get_current_user
from app.main import app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@asynccontextmanager
async def client_for(db: AsyncSession, owner: uuid.UUID) -> AsyncIterator[AsyncClient]:
    async def database() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=owner)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def add_history(
    db: AsyncSession,
    owner: uuid.UUID,
    account: Account,
    *,
    pending: bool = False,
    income: bool = False,
) -> FinancialTransaction:
    kind = "income" if income else "expense"
    category = await service.create_category(db, owner, CategoryCreate(name=kind, type=kind))
    return await service.create_transaction(
        db,
        owner,
        TransactionCreate(
            description=kind,
            type=kind,
            is_pending=pending,
            postings=[
                PostingCreate(
                    account_id=account.id,
                    source_amount=100,
                    base_amount_pln=100,
                    direction="credit" if income else "debit",
                ),
                PostingCreate(
                    category_id=category.id,
                    source_amount=100,
                    base_amount_pln=100,
                    direction="debit" if income else "credit",
                ),
            ],
        ),
    )


@pytest.mark.parametrize("currency", ["EUR", "USD", "eur"])
async def test_patch_empty_account_currency_and_capability(
    db_session: AsyncSession, currency: str
) -> None:
    owner = uuid.uuid4()
    async with client_for(db_session, owner) as client:
        created = await client.post(
            "/api/finance/accounts", json={"name": "Revolut", "type": "checking"}
        )
        assert created.status_code == 201
        account_id = created.json()["id"]
        response = await client.patch(
            f"/api/finance/accounts/{account_id}", json={"currency": currency}
        )
        assert response.status_code == 200
        assert response.json()["currency"] == currency.upper()
        assert response.json()["can_change_currency"] is True
        assert created.json()["can_change_currency"] is True
        detail = await client.get(f"/api/finance/accounts/{account_id}")
        listed = await client.get("/api/finance/accounts")
        assert detail.json()["can_change_currency"] is True
        assert listed.json()[0]["can_change_currency"] is True


@pytest.mark.parametrize("currency", [None, "GBP", "", "EU", "USDD"])
async def test_patch_rejects_invalid_currency_without_other_mutation(
    db_session: AsyncSession, currency: str | None
) -> None:
    owner = uuid.uuid4()
    account = await service.create_account(
        db_session, owner, AccountCreate(name="Original", type="cash")
    )
    async with client_for(db_session, owner) as client:
        response = await client.patch(
            f"/api/finance/accounts/{account.id}", json={"currency": currency, "name": "Changed"}
        )
    assert response.status_code == 422
    await db_session.refresh(account)
    assert (account.name, account.currency) == ("Original", "PLN")


@pytest.mark.parametrize(
    "dependency",
    [
        "posting",
        "pending",
        "zero_balance",
        "schedule",
        "inactive_schedule",
        "mapping",
        "import_source",
    ],
)
async def test_currency_change_conflict_keeps_history_and_metadata(
    db_session: AsyncSession, dependency: str
) -> None:
    owner = uuid.uuid4()
    account = await service.create_account(
        db_session, owner, AccountCreate(name="Original", type="checking")
    )
    if dependency in {"posting", "pending", "zero_balance"}:
        await add_history(db_session, owner, account, pending=dependency == "pending")
        if dependency == "zero_balance":
            await add_history(db_session, owner, account, income=True)
            assert (await service.get_account(db_session, owner, account.id)).balance_source == 0
    elif dependency in {"schedule", "inactive_schedule"}:
        category = await service.create_category(
            db_session, owner, CategoryCreate(name="Rent", type="expense")
        )
        scheduled = await service.create_scheduled_item(
            db_session,
            owner,
            ScheduledFinanceItemCreate(
                name="Rent",
                type="expense",
                account_id=account.id,
                category_id=category.id,
                currency="PLN",
                due_day=5,
                amount_method="fixed",
                fixed_amount_pln=100,
            ),
        )
        if dependency == "inactive_schedule":
            await service.update_scheduled_item(
                db_session, owner, scheduled.id, ScheduledFinanceItemUpdate(is_active=False)
            )
            assert scheduled.is_active is False
    elif dependency == "mapping":
        db_session.add(
            ActualImportMapping(
                user_id=owner,
                entity_type="account",
                entity_id=account.id,
                actual_id="source-account",
            )
        )
    else:
        account.source = "actual"
    await db_session.flush()
    before = [
        (p.id, p.source_currency, p.source_amount)
        for p in (await db_session.execute(select(Posting))).scalars()
    ]
    async with client_for(db_session, owner) as client:
        detail = await client.get(f"/api/finance/accounts/{account.id}")
        assert detail.json()["can_change_currency"] is False
        response = await client.patch(
            f"/api/finance/accounts/{account.id}", json={"currency": "EUR", "name": "Changed"}
        )
        assert response.status_code == 409
        await db_session.refresh(account)
        assert (account.name, account.currency) == ("Original", "PLN")
        # A stale UI re-sending the same currency may still update other metadata.
        same = await client.patch(
            f"/api/finance/accounts/{account.id}", json={"currency": "pln", "name": "Renamed"}
        )
        assert same.status_code == 200
    await db_session.refresh(account)
    assert (account.name, account.currency) == ("Renamed", "PLN")
    after = [
        (p.id, p.source_currency, p.source_amount)
        for p in (await db_session.execute(select(Posting))).scalars()
    ]
    assert before == after


async def test_currency_patch_is_owner_scoped(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    account = await service.create_account(
        db_session, owner, AccountCreate(name="Owned", type="cash")
    )
    async with client_for(db_session, uuid.uuid4()) as client:
        response = await client.patch(
            f"/api/finance/accounts/{account.id}", json={"currency": "EUR"}
        )
    assert response.status_code == 404
    assert account.currency == "PLN"


async def add_dependency(
    db: AsyncSession, owner: uuid.UUID, account: Account, kind: str
) -> FinancialTransaction | ScheduledFinanceItem:
    if kind == "posting":
        return await add_history(db, owner, account)
    category = await service.create_category(db, owner, CategoryCreate(name="Plan", type="expense"))
    return await service.create_scheduled_item(
        db,
        owner,
        ScheduledFinanceItemCreate(
            name="Plan",
            type="expense",
            account_id=account.id,
            category_id=category.id,
            currency="PLN",
            due_day=5,
            amount_method="fixed",
            fixed_amount_pln=100,
        ),
    )


@pytest.mark.parametrize("kind", ["posting", "schedule"])
@pytest.mark.parametrize("first", ["currency", "dependency"])
async def test_first_dependency_and_currency_change_are_serialized(
    db_session: AsyncSession, kind: str, first: str
) -> None:
    owner = uuid.uuid4()
    account = await service.create_account(
        db_session, owner, AccountCreate(name="Race", type="checking")
    )
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with sessions() as one, sessions() as two:
        if first == "currency":
            await service.update_account(one, owner, account.id, AccountUpdate(currency="EUR"))
        else:
            await add_dependency(one, owner, account, kind)
        # A real PostgreSQL timeout proves the second operation waits for the
        # first transaction; no sleep-based or mock-based concurrency assertion.
        await two.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(DBAPIError, match="lock timeout"):
            if first == "currency":
                await add_dependency(two, owner, account, kind)
            else:
                await service.update_account(two, owner, account.id, AccountUpdate(currency="EUR"))
        await two.rollback()
        await one.commit()
        if first == "currency":
            with pytest.raises(ValueError, match="currency"):
                await add_dependency(two, owner, account, kind)
        else:
            with pytest.raises(ValueError, match="currency"):
                await service.update_account(two, owner, account.id, AccountUpdate(currency="EUR"))


@pytest.mark.parametrize("kind", ["posting", "schedule"])
async def test_dependency_validation_refreshes_previously_cached_currency(
    db_session: AsyncSession, kind: str
) -> None:
    owner = uuid.uuid4()
    account = await service.create_account(
        db_session, owner, AccountCreate(name="Cached", type="checking")
    )
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with sessions() as reader, sessions() as changer:
        cached = await service.get_account(reader, owner, account.id)
        assert cached.currency == "PLN"
        await service.update_account(changer, owner, account.id, AccountUpdate(currency="EUR"))
        await changer.commit()
        with pytest.raises(ValueError, match="currency"):
            await add_dependency(reader, owner, cached, kind)
