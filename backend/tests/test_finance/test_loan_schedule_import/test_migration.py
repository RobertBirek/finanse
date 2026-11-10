"""Actual Alembic roundtrip over legacy paid/partial/past-unpaid state and stage A."""

import uuid
from pathlib import Path

import pytest

from tests.migration_fixtures import MigrationDatabase

pytestmark = pytest.mark.migration
OLD_HEAD = "6bd8758ebc7d"


def schedule_head() -> str:
    versions = Path(__file__).resolve().parents[3] / "migrations/versions"
    matches = list(versions.glob("*_loan_schedule_revisions.py"))
    assert len(matches) == 1, "Expected the generated loan schedule migration"
    return matches[0].name.split("_", 1)[0]


async def snapshot(
    database: MigrationDatabase, *, new_columns: bool = False
) -> dict[str, list[str]]:
    result = {}
    tables = await database.connection.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )
    for record in tables:
        name = record["tablename"]
        if name == "alembic_version" or name in {
            "loan_schedule_revisions",
            "loan_schedule_memberships",
        }:
            continue
        assert name.replace("_", "").isalnum()
        exclude = (
            " - 'active_schedule_revision_id'"
            if new_columns and name == "loan_agreements"
            else " - 'superseded_by_revision_id'"
            if new_columns and name == "loan_installments"
            else ""
        )
        rows = await database.connection.fetch(
            f'SELECT (to_jsonb(t){exclude})::text FROM "{name}" t ORDER BY 1'
        )
        result[name] = [row[0] for row in rows]
    return result


async def seed_legacy(database: MigrationDatabase) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """SQL deliberately targets the old schema, not future ORM mappings."""
    db = database.connection
    owner, payer, debt, loan = [uuid.uuid4() for _ in range(4)]
    await db.execute(
        "INSERT INTO users(id,email,password_hash,display_name,is_active) VALUES($1,'schedule-migration@example.test','synthetic-hash','Synthetic',true)",
        owner,
    )
    for account_id, name, kind in [
        (payer, "Synthetic payer", "checking"),
        (debt, "Synthetic debt", "credit"),
    ]:
        await db.execute(
            "INSERT INTO accounts(id,user_id,name,type,currency,source,is_active,is_budget_account,opened_at) VALUES($1,$2,$3,$4,'PLN','manual',true,true,'2020-01-01')",
            account_id,
            owner,
            name,
            kind,
        )
    await db.execute(
        "INSERT INTO loan_agreements(id,user_id,name,account_id,payment_account_id,is_active) VALUES($1,$2,'Synthetic legacy loan',$3,$4,true)",
        loan,
        owner,
        debt,
        payer,
    )
    installment_ids = [uuid.uuid4() for _ in range(3)]
    for number, installment_id in enumerate(installment_ids, 1):
        due = "2026-12-01" if number == 2 else "2020-01-01" if number == 1 else "2020-02-01"
        await db.execute(
            "INSERT INTO loan_installments(id,user_id,loan_id,number,due_date,principal_pln,interest_pln,fees_pln) VALUES($1,$2,$3,$4,$5::text::date,9000,1000,0)",
            installment_id,
            owner,
            loan,
            number,
            due,
        )
    for ordinal, amount in enumerate([10000, 1000]):
        transaction = uuid.uuid4()
        await db.execute(
            "INSERT INTO financial_transactions(id,user_id,date,description,type,source,is_pending,created_by) VALUES($1,$2,'2020-01-01','Synthetic linked transfer','transfer','actual',false,'human')",
            transaction,
            owner,
        )
        for account_id, direction in [(payer, "debit"), (debt, "credit")]:
            await db.execute(
                "INSERT INTO postings(id,transaction_id,account_id,source_amount,source_currency,base_amount_pln,fx_rate,fx_rate_source,direction,is_budget_impact) VALUES($1,$2,$3,$4,'PLN',$4,1,'manual',$5,false)",
                uuid.uuid4(),
                transaction,
                account_id,
                amount,
                direction,
            )
        await db.execute(
            "INSERT INTO loan_payment_links(id,user_id,installment_id,transaction_id) VALUES($1,$2,$3,$4)",
            uuid.uuid4(),
            owner,
            installment_ids[ordinal],
            transaction,
        )
        await db.execute(
            "INSERT INTO actual_import_mappings(id,user_id,entity_type,actual_id,entity_id) VALUES($1,$2,'transaction',$3,$4)",
            uuid.uuid4(),
            owner,
            f"synthetic-schedule-{ordinal}",
            transaction,
        )
    await db.execute(
        "INSERT INTO bank_import_batches(id,user_id,kind) VALUES($1,$2,'statement')",
        uuid.uuid4(),
        owner,
    )
    receipt = uuid.uuid4()
    await db.execute(
        "INSERT INTO finance_command_receipts(id,user_id,action,key,request_hash,response_json,result_ids) VALUES($1,$2,'loan_schedule.activate','synthetic-migration',$3,'{}','[]')",
        receipt,
        owner,
        "a" * 64,
    )
    return owner, loan, receipt


async def test_real_roundtrip_has_no_backfill_or_legacy_mutation(owned_migration_database):
    database = owned_migration_database
    await database.migrate("upgrade", OLD_HEAD)
    owner, loan, receipt = await seed_legacy(database)
    before = await snapshot(database)
    head = schedule_head()
    await database.migrate("upgrade", head)
    assert await snapshot(database, new_columns=True) == before
    for table in ["loan_schedule_revisions", "loan_schedule_memberships"]:
        assert await database.connection.fetchval(f"SELECT count(*) FROM {table}") == 0
    assert (
        await database.connection.fetchval(
            "SELECT count(*) FROM loan_agreements WHERE active_schedule_revision_id IS NOT NULL"
        )
        == 0
    )
    assert (
        await database.connection.fetchval(
            "SELECT count(*) FROM loan_installments WHERE superseded_by_revision_id IS NOT NULL"
        )
        == 0
    )
    await database.migrate("downgrade", OLD_HEAD)
    assert await snapshot(database) == before
    await database.migrate("upgrade", head)
    assert await snapshot(database, new_columns=True) == before
    revision = uuid.uuid4()
    await database.connection.execute(
        "INSERT INTO loan_schedule_revisions(id,user_id,loan_id,ordinal,kind,state,receipt_id,activated_on,cutover_date) VALUES($1,$2,$3,1,'manual_baseline','superseded',$4,'2026-11-10','2026-11-10')",
        revision,
        owner,
        loan,
        receipt,
    )
    with pytest.raises(RuntimeError, match="Cannot downgrade.*loan schedule"):
        await database.migrate("downgrade", OLD_HEAD)
    assert await database.connection.fetchval("SELECT id FROM loan_schedule_revisions") == revision
    assert await snapshot(database, new_columns=True) == before
