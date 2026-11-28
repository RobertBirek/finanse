"""PostgreSQL route and forecast coverage for conditional recurring obligations."""

import importlib.util
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import get_db
from app.finance.conditional_recurring_obligations import create as create_conditional_obligation
from app.finance.entities import create_account, delete_account, update_account
from app.finance.models import ConditionalRecurringObligation, FinancialTransaction, Posting
from app.finance.schemas import AccountCreate, AccountUpdate, ConditionalRecurringObligationCreate
from app.finance.service import get_cashflow_forecast
from app.identity.models import User
from app.identity.router import get_current_user
from app.main import app

ROOT = "/api/finance/cashflow/conditional-obligations"


@asynccontextmanager
async def authenticated_client(db: AsyncSession, owner_id: uuid.UUID) -> AsyncIterator[AsyncClient]:
    """Route requests use a real ASGI application and a synthetic authenticated identity."""

    async def database() -> AsyncIterator[AsyncSession]:
        yield db

    async def current_user() -> SimpleNamespace:
        return SimpleNamespace(id=owner_id)

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = current_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def accounts_for(
    db: AsyncSession, owner_id: uuid.UUID, *, fallback_currency: str = "PLN"
) -> tuple[uuid.UUID, uuid.UUID]:
    if await db.get(User, owner_id) is None:
        db.add(
            User(
                id=owner_id,
                email=f"{owner_id}@example.invalid",
                password_hash="unused",
                display_name="Synthetic",
            )
        )
        await db.flush()
    primary = await create_account(
        db,
        owner_id,
        AccountCreate(name="Synthetic primary", type="checking", currency="EUR"),
    )
    fallback = await create_account(
        db,
        owner_id,
        AccountCreate(name="Synthetic fallback", type="checking", currency=fallback_currency),
    )
    return primary.id, fallback.id


async def direct_obligation(
    db: AsyncSession,
    owner_id: uuid.UUID,
    primary_account_id: uuid.UUID,
    fallback_account_id: uuid.UUID,
    *,
    is_active: bool = True,
) -> ConditionalRecurringObligation:
    record = ConditionalRecurringObligation(
        user_id=owner_id,
        name="Direct conditional obligation",
        condition_key="direct_constraint",
        due_day=15,
        primary_account_id=primary_account_id,
        primary_amount_minor=2_000,
        primary_currency="EUR",
        fallback_account_id=fallback_account_id,
        fallback_amount_minor=8_000,
        fallback_currency="PLN",
        is_active=is_active,
    )
    db.add(record)
    await db.flush()
    return record


def payload(
    primary_account_id: uuid.UUID, fallback_account_id: uuid.UUID, **overrides: object
) -> dict:
    body: dict[str, object] = {
        "name": "Synthetic conditional subscription",
        "condition_key": "synthetic_subscription_eligible",
        "condition_state": "unknown",
        "cadence": "monthly",
        "due_day": 15,
        "primary_account_id": str(primary_account_id),
        "primary_amount_minor": 2_000,
        "primary_currency": "EUR",
        "fallback_account_id": str(fallback_account_id),
        "fallback_amount_minor": 8_000,
        "fallback_currency": "PLN",
    }
    body.update(overrides)
    return body


async def ledger_counts(db: AsyncSession) -> tuple[int, int]:
    return (
        (await db.scalar(select(func.count()).select_from(FinancialTransaction))) or 0,
        (await db.scalar(select(func.count()).select_from(Posting))) or 0,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_authenticated_owner_cannot_list_patch_or_delete_another_owners_obligation(
    db_session: AsyncSession,
) -> None:
    """Fails if an obligation query loses its owner predicate."""

    owner_id, other_owner_id = uuid.uuid4(), uuid.uuid4()
    primary, fallback = await accounts_for(db_session, owner_id)
    foreign_primary, foreign_fallback = await accounts_for(db_session, other_owner_id)

    async with authenticated_client(db_session, other_owner_id) as other_client:
        foreign = await other_client.post(ROOT, json=payload(foreign_primary, foreign_fallback))
    assert foreign.status_code == 201
    foreign_id = foreign.json()["id"]

    async with authenticated_client(db_session, owner_id) as client:
        listing = await client.get(ROOT)
        patch = await client.patch(f"{ROOT}/{foreign_id}", json={"fallback_amount_minor": None})
        delete = await client.delete(f"{ROOT}/{foreign_id}")
        owned = await client.post(ROOT, json=payload(primary, fallback))

    assert listing.status_code == 200
    assert listing.json() == []
    assert patch.status_code == 404
    assert delete.status_code == 404
    assert owned.status_code == 201


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_rejects_an_account_with_a_different_native_currency(
    db_session: AsyncSession,
) -> None:
    """Fails if native amounts can be bound to an account in another currency."""

    owner_id = uuid.uuid4()
    primary, fallback = await accounts_for(db_session, owner_id, fallback_currency="USD")

    async with authenticated_client(db_session, owner_id) as client:
        response = await client.post(ROOT, json=payload(primary, fallback))

    assert response.status_code == 422
    assert (
        response.json()["detail"] == "Fallback obligation currency does not match account currency"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_patch_preserve_an_explicitly_unknown_fallback_without_ledger_writes(
    db_session: AsyncSession,
) -> None:
    """Fails if PATCH null is discarded or declarations create ledger records."""

    owner_id = uuid.uuid4()
    primary, fallback = await accounts_for(db_session, owner_id)
    before = await ledger_counts(db_session)

    async with authenticated_client(db_session, owner_id) as client:
        created = await client.post(
            ROOT, json=payload(primary, fallback, fallback_amount_minor=None)
        )
        valued = await client.patch(
            f"{ROOT}/{created.json()['id']}", json={"fallback_amount_minor": 8_000}
        )
        patched = await client.patch(
            f"{ROOT}/{created.json()['id']}", json={"fallback_amount_minor": None}
        )
        listed = await client.get(ROOT)

    assert created.status_code == 201
    assert created.json()["fallback_amount_minor"] is None
    assert valued.status_code == 200
    assert valued.json()["fallback_amount_minor"] == 8_000
    assert patched.status_code == 200
    assert patched.json()["fallback_amount_minor"] is None
    assert listed.json() == [patched.json()]
    assert await ledger_counts(db_session) == before


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unknown_conditional_obligation_is_excluded_from_forecast_and_hides_safe_limit(
    db_session: AsyncSession,
) -> None:
    """Fails if an unknown condition is assigned a PLN forecast or a safe limit."""

    owner_id = uuid.uuid4()
    primary, fallback = await accounts_for(db_session, owner_id)
    async with authenticated_client(db_session, owner_id) as client:
        created = await client.post(
            ROOT,
            json=payload(primary, fallback, due_day=21, condition_state="unknown"),
        )
    assert created.status_code == 201
    before = await ledger_counts(db_session)

    forecast = await get_cashflow_forecast(db_session, owner_id, today=date(2026, 11, 20))

    assert forecast.safe_daily_limit_pln is None
    assert forecast.has_excluded_obligations_before_payday is True
    assert forecast.excluded_obligation_reasons == ["conditional_obligation_unresolved"]
    assert [
        (
            suggestion.status,
            suggestion.amount_minor,
            suggestion.amount_pln,
            suggestion.included_in_forecast,
            suggestion.exclusion_reasons,
        )
        for suggestion in forecast.suggestions
    ] == [
        (
            "condition_unresolved",
            None,
            None,
            False,
            ["conditional_obligation_unresolved"],
        )
    ]
    assert await ledger_counts(db_session) == before


@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_rejects_a_direct_cross_owner_account_reference(
    db_session: AsyncSession,
) -> None:
    """Fails if a direct insert can bind an owner's obligation to another owner's account."""

    owner_id, other_owner_id = uuid.uuid4(), uuid.uuid4()
    primary, fallback = await accounts_for(db_session, owner_id)
    foreign_primary, _foreign_fallback = await accounts_for(db_session, other_owner_id)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await direct_obligation(db_session, owner_id, foreign_primary, fallback)

    await direct_obligation(db_session, owner_id, primary, fallback)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("account_role", "is_active"),
    [("primary", True), ("fallback", True), ("primary", False), ("fallback", False)],
)
async def test_conditional_obligation_blocks_account_currency_changes_and_deletion(
    db_session: AsyncSession, account_role: str, is_active: bool
) -> None:
    """Fails if any conditional declaration stops protecting either account transition."""

    owner_id = uuid.uuid4()
    primary, fallback = await accounts_for(db_session, owner_id)
    await direct_obligation(db_session, owner_id, primary, fallback, is_active=is_active)
    account_id = primary if account_role == "primary" else fallback

    with pytest.raises(ValueError, match="currency"):
        await update_account(db_session, owner_id, account_id, AccountUpdate(currency="USD"))
    with pytest.raises(ValueError, match="records"):
        await delete_account(db_session, owner_id, account_id)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["account", "obligation"])
@pytest.mark.parametrize(
    ("account_update", "creation_error", "account_error"),
    [
        (AccountUpdate(currency="USD"), "currency", "currency"),
        (AccountUpdate(is_active=False), "active budget", "conditional obligation"),
        (
            AccountUpdate(is_budget_account=False),
            "active budget",
            "conditional obligation",
        ),
    ],
)
async def test_conditional_obligation_creation_and_account_dependency_changes_are_serialized(
    db_session: AsyncSession,
    first: str,
    account_update: AccountUpdate,
    creation_error: str,
    account_error: str,
) -> None:
    """Fails if creation can race currency, active-state, or budget-state transitions."""

    owner_id = uuid.uuid4()
    primary, fallback = await accounts_for(db_session, owner_id)
    data = ConditionalRecurringObligationCreate(
        name="Serialized conditional obligation",
        condition_key="serialized_currency",
        due_day=15,
        primary_account_id=primary,
        primary_amount_minor=2_000,
        primary_currency="EUR",
        fallback_account_id=fallback,
        fallback_amount_minor=8_000,
        fallback_currency="PLN",
    )
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async with sessions() as one, sessions() as two:
        if first == "account":
            await update_account(one, owner_id, primary, account_update)
        else:
            await create_conditional_obligation(one, owner_id, data)

        await two.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(DBAPIError, match="lock timeout"):
            if first == "account":
                await create_conditional_obligation(two, owner_id, data)
            else:
                await update_account(two, owner_id, primary, account_update)
        await two.rollback()
        await one.commit()

        if first == "account":
            with pytest.raises(ValueError, match=creation_error):
                await create_conditional_obligation(two, owner_id, data)
        else:
            with pytest.raises(ValueError, match=account_error):
                await update_account(two, owner_id, primary, account_update)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("account_role", ["primary", "fallback"])
@pytest.mark.parametrize("obligation_is_active", [True, False])
@pytest.mark.parametrize(
    ("account_update", "field_name", "account_field"),
    [
        (AccountUpdate(is_active=False), "active", "is_active"),
        (AccountUpdate(is_budget_account=False), "budget", "is_budget_account"),
    ],
)
async def test_conditional_obligation_blocks_disabling_or_unbudgeting_either_account(
    db_session: AsyncSession,
    account_role: str,
    obligation_is_active: bool,
    account_update: AccountUpdate,
    field_name: str,
    account_field: str,
) -> None:
    """Fails if either variant can lose required account eligibility after declaration."""

    owner_id = uuid.uuid4()
    primary, fallback = await accounts_for(db_session, owner_id)
    await direct_obligation(db_session, owner_id, primary, fallback, is_active=obligation_is_active)
    account_id = primary if account_role == "primary" else fallback

    with pytest.raises(ValueError, match="conditional obligation"):
        await update_account(db_session, owner_id, account_id, account_update)

    account = await create_account(
        db_session, owner_id, AccountCreate(name=f"Unrelated {field_name}", type="cash")
    )
    updated = await update_account(db_session, owner_id, account.id, account_update)
    assert updated is not None
    assert getattr(updated, account_field) is False


def test_conditional_obligation_migration_downgrade_refuses_populated_table_before_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fails if downgrade drops persisted declarations instead of refusing safely."""

    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/c3d4e5f6a7b8_conditional_recurring_obligations.py"
    )
    spec = importlib.util.spec_from_file_location("conditional_obligation_revision", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    queries: list[str] = []
    ddl: list[str] = []

    class Connection:
        def execute(self, query: object) -> None:
            queries.append(str(query))

        def scalar(self, query: object) -> bool:
            queries.append(str(query))
            return True

    class Recorder:
        def get_bind(self) -> Connection:
            return Connection()

        def __getattr__(self, name: str):
            return lambda *args, **kwargs: ddl.append(name)

    monkeypatch.setattr(migration, "op", Recorder())

    with pytest.raises(RuntimeError, match="conditional recurring obligations"):
        migration.downgrade()

    assert "ACCESS EXCLUSIVE" in queries[0]
    assert "conditional_recurring_obligations" in queries[1]
    assert ddl == []
