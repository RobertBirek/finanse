"""Real UP must add zero BO without rewriting any existing financial fact."""

import uuid
from datetime import date

import pytest

from tests import migration_fixtures

owned_migration_database = migration_fixtures.owned_migration_database


@pytest.mark.migration
async def test_opening_backfill_preserves_history(owned_migration_database):
    database = owned_migration_database
    await database.migrate("upgrade", "2c77e935ee39")
    db = database.connection
    owner = uuid.uuid4()
    accounts = []
    for kind in ["checking", "savings", "cash", "credit", "credit_card", "investment"]:
        for currency in ["PLN", "EUR", "USD"]:
            account = uuid.uuid4()
            accounts.append(account)
            await db.execute(
                "INSERT INTO accounts(id,user_id,name,type,currency,source,is_active,"
                "is_budget_account,opened_at) VALUES($1,$2,$3,$4,$5,'actual',$6,true,'2020-01-03')",
                account,
                owner,
                f"{kind}-{currency}",
                kind,
                currency,
                len(accounts) % 2 == 0,
            )
    txn = uuid.uuid4()
    await db.execute(
        "INSERT INTO financial_transactions(id,user_id,date,description,type,source,"
        "is_pending,created_by) VALUES($1,$2,'2020-01-03','[BO] Bilans otwarcia',"
        "'transfer','actual',false,'human')",
        txn,
        owner,
    )
    for account, direction in [(accounts[0], "credit"), (accounts[3], "debit")]:
        await db.execute(
            "INSERT INTO postings(id,transaction_id,account_id,source_amount,source_currency,"
            "base_amount_pln,fx_rate,fx_rate_source,direction,is_budget_impact) "
            "VALUES($1,$2,$3,125050,'PLN',125050,1,'manual',$4,false)",
            uuid.uuid4(),
            txn,
            account,
            direction,
        )
    tables = await db.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'alembic_version'"
    )
    before = {
        r["tablename"]: await db.fetch(f'SELECT * FROM "{r["tablename"]}" ORDER BY id')
        for r in tables
    }
    await database.migrate("upgrade", "head")
    assert await db.fetchval("SELECT to_regclass('account_opening_balances')") is not None
    records = await db.fetch("SELECT * FROM account_opening_balances")
    assert {r["account_id"] for r in records} == set(accounts)
    assert all(
        r["transaction_id"] is None
        and r["version"] == 1
        and r["opening_date"] == date(2020, 1, 3)
        and r["user_id"] == owner
        for r in records
    )
    for table, rows in before.items():
        assert await db.fetch(f'SELECT * FROM "{table}" ORDER BY id') == rows
    # Re-running UP cannot duplicate BO or introduce fake zero postings.
    await database.migrate("upgrade", "head")
    assert await db.fetchval("SELECT count(*) FROM account_opening_balances") == 18
    assert await db.fetchval("SELECT count(*) FROM postings") == 2
    await db.execute(
        "UPDATE account_opening_balances SET transaction_id=$1 WHERE account_id=$2",
        txn,
        accounts[0],
    )
    with pytest.raises(RuntimeError, match="nonzero opening balances must be retained"):
        await database.migrate("downgrade", "2c77e935ee39")
    assert await db.fetchval("SELECT count(*) FROM account_opening_balances") == 18
    assert await db.fetchval("SELECT count(*) FROM postings") == 2
