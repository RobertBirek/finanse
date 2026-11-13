"""The additive migration preserves old ledger rows and refuses lossy rollback."""

import uuid

import pytest

from tests.migration_fixtures import MigrationDatabase
from tests.migration_fixtures import owned_migration_database as _owned_migration_database

owned_migration_database = _owned_migration_database
pytestmark = [pytest.mark.migration, pytest.mark.asyncio]


async def test_person_upgrade_preserves_every_old_table_and_guards_downgrade(
    owned_migration_database: MigrationDatabase,
):
    db = owned_migration_database
    await db.migrate("upgrade", "3254a4781542")
    owner, account, person = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await db.connection.execute(
        "INSERT INTO accounts(id,user_id,name,type,currency,source,is_active,is_budget_account) "
        "VALUES($1,$2,'Preserved','checking','PLN','manual',true,false)",
        account,
        owner,
    )
    tables = await db.connection.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'alembic_version'"
    )

    async def snapshots():
        return {
            row[0]: await db.connection.fetchval(
                f'''SELECT coalesce(string_agg(row_to_json(t)::text, '\n' ORDER BY row_to_json(t)::text),'') FROM "{row[0]}" t'''
            )
            for row in tables
        }

    before = await snapshots()
    await db.migrate("upgrade", "head")
    assert await snapshots() == before
    assert await db.connection.fetchval("SELECT count(*) FROM finance_people") == 0
    await db.migrate("downgrade", "3254a4781542")
    assert await snapshots() == before
    await db.migrate("upgrade", "head")
    await db.connection.execute(
        "INSERT INTO finance_people(id,user_id,name,is_active,version,reference_account_id) VALUES($1,$2,'Person',true,1,$3)",
        person,
        owner,
        account,
    )
    with pytest.raises(RuntimeError, match="populated"):
        await db.migrate("downgrade", "3254a4781542")
    assert await db.connection.fetchval("SELECT count(*) FROM finance_people") == 1
