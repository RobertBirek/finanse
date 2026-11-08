"""Accounts and their card terms form one owned, atomic write; list is ledger-backed."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, func, select

from app.finance import service
from app.finance.credit_card_models import CreditCard
from app.finance.models import Account, FinancialTransaction, Posting
from app.finance.schemas import AccountCreate, TransactionUpdate
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_credit_cards import config, debit, setup

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ACCOUNTS = "/api/finance/accounts"


async def test_account_create_saves_independent_card_terms_and_returns_them(db_session):
    owner, _, _, _ = await setup(db_session)
    async with client_for(db_session, owner) as client:
        first = await client.post(
            ACCOUNTS,
            json={
                "name": "First card",
                "type": "credit_card",
                "credit_card": config(),
            },
        )
        assert first.status_code == 201, first.text
        second = await client.post(
            ACCOUNTS,
            json={
                "name": "Second card",
                "type": "credit_card",
                "credit_card": {**config(), "limit_pln": 1200000, "apr": "9.25"},
            },
        )
        assert second.status_code == 201, second.text
        assert first.json()["type"] == second.json()["type"] == "credit_card"
        assert first.json()["credit_card"]["limit_pln"] == 3360000
        assert second.json()["credit_card"]["limit_pln"] == 1200000
        assert second.json()["credit_card"]["apr"] == "9.2500"
        assert first.json()["credit_card"]["version"] == 1
        assert first.json()["can_change_currency"] is False
        assert "plans" not in first.json()["credit_card"]
        fetched = (await client.get(ACCOUNTS)).json()
        assert (
            next(a for a in fetched if a["id"] == first.json()["id"])["credit_card"]
            == first.json()["credit_card"]
        )
    assert await db_session.scalar(select(func.count()).select_from(CreditCard)) == 2
    assert await db_session.scalar(select(func.count()).select_from(Posting)) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"credit_card": None},
        {"credit_card": {**config(), "expected_version": 2}},
        {"credit_card": {**config(), "limit_pln": 0}},
        {"currency": "EUR"},
        {"is_active": False},
    ],
)
async def test_invalid_create_does_not_leave_a_partial_account_or_profile(db_session, changes):
    owner, _, _, _ = await setup(db_session)
    before = await db_session.scalar(select(func.count()).select_from(Account))
    async with client_for(db_session, owner) as client:
        response = await client.post(
            ACCOUNTS,
            json={
                "name": "Invalid card",
                "type": "credit_card",
                "credit_card": config(),
                **changes,
            },
        )
        assert response.status_code in {409, 422}, response.text
    assert await db_session.scalar(select(func.count()).select_from(Account)) == before
    assert await db_session.scalar(select(func.count()).select_from(CreditCard)) == 0


async def test_new_card_type_requires_terms_but_generic_credit_remains_independent(db_session):
    owner, _, _, _ = await setup(db_session)
    async with client_for(db_session, owner) as client:
        assert (
            await client.post(ACCOUNTS, json={"name": "No terms", "type": "credit_card"})
        ).status_code == 422
        generic = await client.post(ACCOUNTS, json={"name": "Loan", "type": "credit"})
        assert generic.status_code == 201
        assert generic.json()["credit_card"] is None
        mismatch = await client.post(
            ACCOUNTS, json={"name": "Wrong type", "type": "checking", "credit_card": config()}
        )
        assert mismatch.status_code == 422


async def test_convert_existing_account_preserves_postings_and_patch_omission_preserves_terms(
    db_session,
):
    owner, account, _, category = await setup(db_session)
    source = await debit(db_session, owner, account, category)
    url = f"{ACCOUNTS}/{account.id}"
    async with client_for(db_session, owner) as client:
        response = await client.patch(url, json={"type": "credit_card", "credit_card": config()})
        assert response.status_code == 200, response.text
        assert response.json()["type"] == "credit_card"
        assert response.json()["credit_card"]["version"] == 1
        assert response.json()["balance_pln"] == -100000
        changed = await client.patch(url, json={"color": "#123456", "name": "Renamed"})
        assert changed.status_code == 200
        assert changed.json()["credit_card"] == response.json()["credit_card"]
        assert (await client.get(url)).json()["name"] == "Renamed"
        assert (
            await client.patch(url, json={"credit_card": None, "name": "Lost"})
        ).status_code == 422
        assert (await client.patch(url, json={"type": "checking"})).status_code == 409
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 1
    assert await db_session.scalar(select(func.count()).select_from(Posting)) == 2
    assert await db_session.get(FinancialTransaction, source.id) is source


async def test_stale_card_version_rolls_back_account_and_terms_together(db_session):
    owner, account, _, _ = await setup(db_session)
    url = f"{ACCOUNTS}/{account.id}"
    async with client_for(db_session, owner) as client:
        old = await client.put(url + "/credit-card", json=config())
        assert old.status_code == 200
        response = await client.patch(
            url,
            json={
                "name": "Partial update",
                "credit_card": {**config(), "limit_pln": 100},
            },
        )
        assert response.status_code == 409, response.text
        current = (await client.get(url)).json()
        assert current["name"] == "VELOBANK - karta"
        assert current["credit_card"]["limit_pln"] == 3360000
        assert current["credit_card"]["version"] == 1
        response = await client.patch(
            url,
            json={
                "name": "Both updated",
                "credit_card": {**config(), "expected_version": 1, "limit_pln": 2000000},
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["name"] == "Both updated"
        assert response.json()["credit_card"]["version"] == 2
        assert response.json()["credit_card"]["limit_pln"] == 2000000


async def test_summary_list_is_owned_multi_card_current_and_has_bounded_queries(
    db_session, monkeypatch
):
    owner, first, _, category = await setup(db_session)
    await debit(db_session, owner, first, category)
    pending = await debit(db_session, owner, first, category, 10000)
    await service.update_transaction(
        db_session, owner, pending.id, TransactionUpdate(is_pending=True)
    )
    future = await debit(db_session, owner, first, category, 30000)
    await service.update_transaction(
        db_session,
        owner,
        future.id,
        TransactionUpdate(transaction_date=datetime.now(UTC).date() + timedelta(days=10)),
    )
    async with client_for(db_session, owner) as client:
        assert (
            await client.put(f"{ACCOUNTS}/{first.id}/credit-card", json=config())
        ).status_code == 200
        second = await client.post(
            ACCOUNTS,
            json={
                "name": "Second card",
                "type": "credit_card",
                "credit_card": {**config(), "limit_pln": 900000},
            },
        )
        assert second.status_code == 201, second.text
        second_id = second.json()["id"]
        assert (
            await client.patch(f"{ACCOUNTS}/{second_id}", json={"is_active": False})
        ).status_code == 200
        await client.post(ACCOUNTS, json={"name": "Not a card", "type": "credit"})
    other, other_card, _, _ = await setup(db_session)
    async with client_for(db_session, other) as client:
        assert (
            await client.put(f"{ACCOUNTS}/{other_card.id}/credit-card", json=config())
        ).status_code == 200

    from app.finance import credit_cards

    async def no_detail(*args, **kwargs):
        raise AssertionError("Summary must not load per-card history")

    monkeypatch.setattr(credit_cards, "detail", no_detail)
    statements = []
    engine = db_session.bind.sync_engine

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        async with client_for(db_session, owner) as client:
            response = await client.get("/api/finance/credit-cards")
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    assert len(statements) <= 3
    rows = {r["account_id"]: r for r in response.json()}
    assert set(rows) == {str(first.id), second_id}
    assert rows[str(first.id)]["debt_pln"] == 100000
    assert rows[str(first.id)]["pending_debits_pln"] == 10000
    assert rows[str(first.id)]["available_pln"] == 3250000
    assert rows[second_id]["is_active"] is False
    assert rows[second_id]["debt_pln"] == 0
    assert rows[second_id]["available_pln"] == 900000
    assert all("plans" not in r and "statements" not in r for r in rows.values())


async def test_card_account_patch_is_owner_scoped_and_unknown_card_list_is_empty(db_session):
    _owner, account, _, _ = await setup(db_session)
    async with client_for(db_session, uuid.uuid4()) as client:
        response = await client.patch(
            f"{ACCOUNTS}/{account.id}", json={"type": "credit_card", "credit_card": config()}
        )
        assert response.status_code == 404
        response = await client.get("/api/finance/credit-cards")
        assert response.status_code == 200 and response.json() == []
    await db_session.refresh(account)
    assert account.type == "checking"


async def test_card_list_denies_anonymous_access(async_client):
    assert (await async_client.get("/api/finance/credit-cards")).status_code == 401


async def test_type_migration_only_reclassifies_owned_existing_profiles_and_preserves_rows(
    db_session,
):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text

    from app.finance import credit_cards
    from app.finance.credit_card_schemas import CardConfig

    owner, account, _, category = await setup(db_session)
    await debit(db_session, owner, account, category)
    await credit_cards.configure(db_session, owner, account.id, CardConfig(**config()))
    generic = await service.create_account(
        db_session, owner, AccountCreate(name="Credit card in name only", type="credit")
    )
    await db_session.execute(
        text("UPDATE accounts SET type='credit' WHERE id=:id"), {"id": account.id}
    )
    before_postings = (await db_session.execute(text("SELECT * FROM postings ORDER BY id"))).all()
    before_profiles = (
        await db_session.execute(text("SELECT * FROM credit_cards ORDER BY id"))
    ).all()
    before_names = (
        await db_session.execute(text("SELECT id,name,currency FROM accounts ORDER BY id"))
    ).all()
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/739144d5eaef_credit_card_account_type.py"
    )
    spec = importlib.util.spec_from_file_location("card_type_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    connection = await db_session.connection()

    def run_upgrade(conn):
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()

    await connection.run_sync(run_upgrade)
    types = dict((await db_session.execute(text("SELECT id,type FROM accounts"))).all())
    assert types[account.id] == "credit_card"
    assert types[generic.id] == "credit"
    assert (
        await db_session.execute(text("SELECT * FROM postings ORDER BY id"))
    ).all() == before_postings
    assert (
        await db_session.execute(text("SELECT * FROM credit_cards ORDER BY id"))
    ).all() == before_profiles
    assert (
        await db_session.execute(text("SELECT id,name,currency FROM accounts ORDER BY id"))
    ).all() == before_names

    def run_downgrade(conn):
        migration.op = Operations(MigrationContext.configure(conn))
        migration.downgrade()

    await connection.run_sync(run_downgrade)
    assert (
        await db_session.scalar(text("SELECT type FROM accounts WHERE id=:id"), {"id": account.id})
        == "credit"
    )
    assert (
        await db_session.execute(text("SELECT * FROM credit_cards ORDER BY id"))
    ).all() == before_profiles
