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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.finance.entities import create_account
from app.finance.models import FinancialTransaction, Posting
from app.finance.schemas import AccountCreate
from app.finance.service import get_cashflow_forecast
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
