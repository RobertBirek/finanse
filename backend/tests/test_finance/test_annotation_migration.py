"""Exercise actual Alembic upgrades against owned disposable databases."""

import uuid

import pytest

from tests.migration_fixtures import MigrationDatabase
from tests.migration_fixtures import owned_migration_database as _owned_migration_database

owned_migration_database = _owned_migration_database

pytestmark = [pytest.mark.migration, pytest.mark.asyncio]


async def test_annotation_upgrade_from_previous_head_preserves_source(
    owned_migration_database: MigrationDatabase,
):
    database = owned_migration_database
    await database.migrate("upgrade", "84fdbd10aa18")
    txn_id, owner = uuid.uuid4(), uuid.uuid4()
    await database.connection.execute(
        "INSERT INTO financial_transactions(id,user_id,date,description,type,is_pending,created_by,source) VALUES($1,$2,'2026-01-01','[actual:keep] source','expense',false,'human','actual')",
        txn_id,
        owner,
    )
    before = await database.connection.fetchval(
        "SELECT row_to_json(t)::text FROM financial_transactions t WHERE id=$1", txn_id
    )
    await database.migrate("upgrade", "head")
    assert (
        await database.connection.fetchval(
            "SELECT row_to_json(t)::text FROM financial_transactions t WHERE id=$1", txn_id
        )
        == before
    )
    assert await database.connection.fetchval("SELECT count(*) FROM transaction_annotations") == 0


@pytest.mark.parametrize("reference", ["missing", "foreign"])
async def test_annotation_upgrade_rejects_invalid_project_without_fixing_data(
    owned_migration_database: MigrationDatabase, reference
):
    database = owned_migration_database
    await database.migrate("upgrade", "84fdbd10aa18")
    txn_id, owner, project_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    if reference == "foreign":
        await database.connection.execute(
            "INSERT INTO projects(id,user_id,name,status) VALUES($1,$2,'Other','active')",
            project_id,
            uuid.uuid4(),
        )
    await database.connection.execute(
        "INSERT INTO financial_transactions(id,user_id,project_id,date,description,type,is_pending,created_by,source) VALUES($1,$2,$3,'2026-01-01','keep','expense',false,'human','actual')",
        txn_id,
        owner,
        project_id,
    )
    with pytest.raises(RuntimeError, match="invalid project references"):
        await database.migrate("upgrade", "head")
    assert (
        await database.connection.fetchval(
            "SELECT project_id FROM financial_transactions WHERE id=$1", txn_id
        )
        == project_id
    )
    assert (
        await database.connection.fetchval("SELECT version_num FROM alembic_version")
        == "84fdbd10aa18"
    )
