import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests import migration_fixtures

owned_migration_database = migration_fixtures.owned_migration_database


def test_loan_migration_remains_in_the_single_head_lineage() -> None:
    backend = Path(__file__).resolve().parents[2]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    assert len(scripts.get_heads()) == 1
    assert "2f4b2c2a527c" in {revision.revision for revision in scripts.walk_revisions()}
    assert scripts.get_revision("2f4b2c2a527c").down_revision == "92eef8e8086c"
    assert scripts.get_revision("c2d7e9a4f801").down_revision == "b8e4c2f1a7d9"


@pytest.mark.migration
async def test_loan_migration_preserves_old_records(
    owned_migration_database: migration_fixtures.MigrationDatabase,
) -> None:
    database = owned_migration_database
    await database.migrate("upgrade", "b8e4c2f1a7d9")
    db = database.connection
    owner, debt, payer, legacy, transaction = [uuid.uuid4() for _ in range(5)]
    for account, name, kind in [
        (legacy, "Legacy", "cash"),
        (debt, "Old debt", "credit"),
        (payer, "Old payer", "checking"),
    ]:
        await db.execute(
            "INSERT INTO accounts(id,user_id,name,type,currency,source,is_active,is_budget_account) VALUES($1,$2,$3,$4,'PLN','manual',true,true)",
            account,
            owner,
            name,
            kind,
        )
    await db.execute(
        "INSERT INTO financial_transactions(id,user_id,date,description,type,source,is_pending,created_by) VALUES($1,$2,'2020-01-03','Synthetic transfer','transfer','manual',false,'human')",
        transaction,
        owner,
    )
    for account, direction in [(payer, "debit"), (debt, "credit")]:
        await db.execute(
            "INSERT INTO postings(id,transaction_id,account_id,source_amount,source_currency,base_amount_pln,fx_rate,fx_rate_source,direction,is_budget_impact) VALUES($1,$2,$3,12345,'PLN',12345,1,'manual',$4,false)",
            uuid.uuid4(),
            transaction,
            account,
            direction,
        )
    tables = ("accounts", "financial_transactions", "postings", "actual_import_mappings")
    before = [await db.fetch(f'SELECT * FROM "{table}" ORDER BY id') for table in tables]
    for command, revision in [
        ("upgrade", "c2d7e9a4f801"),
        ("downgrade", "b8e4c2f1a7d9"),
        ("upgrade", "c2d7e9a4f801"),
    ]:
        await database.migrate(command, revision)
        assert [
            await db.fetch(f'SELECT * FROM "{table}" ORDER BY id') for table in tables
        ] == before
    assert await db.fetchval("SELECT count(*) FROM loan_agreements") == 0
