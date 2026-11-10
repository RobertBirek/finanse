"""Bill migration roundtrip in an exclusively owned scratch database."""

import pytest

from tests import migration_fixtures

owned_migration_database = migration_fixtures.owned_migration_database

PREVIOUS_REVISION = "c2d7e9a4f801"
CURRENT_REVISION = "7f8ce92bda94"
NEW_TABLES = {
    "document_extraction_revisions",
    "document_payment_allocations",
    "finance_command_receipts",
    "financial_document_sources",
    "financial_documents",
    "recurring_occurrence_coverages",
}
REQUIRED_CONSTRAINTS = {
    "ck_financial_document_approved_complete",
    "ck_document_payment_allocation_amount",
    "uq_financial_document_source_document",
    "uq_document_payment_allocation",
    "uq_recurring_coverage_occurrence",
    "uq_document_extraction_revision",
}


@pytest.mark.migration
async def test_migration_preserves_old_rows_without_backfill(
    owned_migration_database: migration_fixtures.MigrationDatabase,
) -> None:
    database = owned_migration_database
    await database.migrate("upgrade", PREVIOUS_REVISION)
    await database.connection.execute(
        "INSERT INTO accounts "
        "(id,user_id,name,type,currency,source,is_active,is_budget_account,opened_at) "
        "VALUES ('00000000-0000-0000-0000-000000000001',"
        "'00000000-0000-0000-0000-000000000002','synthetic-preservation-row',"
        "'checking','PLN','manual',true,true,CURRENT_DATE)"
    )
    await database.migrate("upgrade", CURRENT_REVISION)
    assert await existing_account_name(database) == "synthetic-preservation-row"
    assert await public_tables(database) >= NEW_TABLES
    assert REQUIRED_CONSTRAINTS <= await financial_document_constraints(database)

    await database.migrate("downgrade", PREVIOUS_REVISION)
    assert (await public_tables(database)).isdisjoint(NEW_TABLES)
    assert await existing_account_name(database) == "synthetic-preservation-row"

    await database.migrate("upgrade", CURRENT_REVISION)
    assert await public_tables(database) >= NEW_TABLES
    assert await existing_account_name(database) == "synthetic-preservation-row"


async def existing_account_name(database: migration_fixtures.MigrationDatabase) -> str:
    return str(
        await database.connection.fetchval(
            "SELECT name FROM accounts WHERE id='00000000-0000-0000-0000-000000000001'"
        )
    )


async def public_tables(database: migration_fixtures.MigrationDatabase) -> set[str]:
    return {
        row[0]
        for row in await database.connection.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        )
    }


async def financial_document_constraints(
    database: migration_fixtures.MigrationDatabase,
) -> set[str]:
    return {
        row[0]
        for row in await database.connection.fetch(
            "SELECT conname FROM pg_constraint WHERE conrelid IN ("
            "'financial_documents'::regclass,'financial_document_sources'::regclass,"
            "'document_payment_allocations'::regclass,'recurring_occurrence_coverages'::regclass,"
            "'document_extraction_revisions'::regclass)"
        )
    }
