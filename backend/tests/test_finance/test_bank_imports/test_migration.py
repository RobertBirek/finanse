"""A metadata create_all cannot prove preservation by an actual Alembic upgrade."""

import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.documents.models import Document
from app.finance.entities import create_account
from app.finance.loan_schemas import LoanCreate, LoanInstallmentCreate
from app.finance.loans import create_loan, create_loan_installment, link_loan_payment
from app.finance.models import ActualImportMapping
from app.finance.schemas import AccountCreate, PostingCreate, TransactionCreate
from app.finance.transactions import create_transaction
from tests.migration_fixtures import MigrationDatabase

pytestmark = pytest.mark.migration


def new_revision() -> str:
    backend = Path(__file__).resolve().parents[3]
    paths = list((backend / "migrations/versions").glob("*_bank_import_staging.py"))
    assert len(paths) == 1, "Expected the autogen bank-import staging migration"
    return paths[0].name.split("_", 1)[0]


async def snapshot(database: MigrationDatabase) -> dict[str, list[str]]:
    records = await database.connection.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )
    result = {}
    for record in records:
        name = record["tablename"]
        if name == "alembic_version" or name.startswith("bank_import_"):
            continue
        assert name.replace("_", "").isalnum()
        result[name] = [
            row[0]
            for row in await database.connection.fetch(
                f'SELECT row_to_json(t)::text FROM "{name}" t ORDER BY row_to_json(t)::text'
            )
        ]
    return result


async def seed_legacy_finance(database: MigrationDatabase, owner: uuid.UUID) -> None:
    engine = create_async_engine(database.url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            payer = await create_account(
                db, owner, AccountCreate(name="Synthetic payer", type="checking")
            )
            debt = await create_account(
                db, owner, AccountCreate(name="Synthetic debt", type="credit")
            )
            transfer = await create_transaction(
                db,
                owner,
                TransactionCreate(
                    transaction_date="2020-01-03",
                    description="Synthetic historical transfer",
                    type="transfer",
                    source="actual",
                    postings=[
                        PostingCreate(
                            account_id=payer.id,
                            source_amount=10000,
                            base_amount_pln=10000,
                            direction="debit",
                        ),
                        PostingCreate(
                            account_id=debt.id,
                            source_amount=10000,
                            base_amount_pln=10000,
                            direction="credit",
                        ),
                    ],
                ),
            )
            loan = await create_loan(
                db,
                owner,
                LoanCreate(
                    name="Synthetic legacy loan", account_id=debt.id, payment_account_id=payer.id
                ),
            )
            installment = await create_loan_installment(
                db,
                owner,
                loan.id,
                LoanInstallmentCreate(
                    number=1,
                    due_date="2020-01-03",
                    principal_pln=9000,
                    interest_pln=1000,
                    fees_pln=0,
                ),
            )
            await link_loan_payment(db, owner, loan.id, installment.id, transfer.id)
            db.add(
                ActualImportMapping(
                    user_id=owner,
                    entity_type="transaction",
                    actual_id="synthetic-historical-reference",
                    entity_id=transfer.id,
                )
            )
            db.add(
                Document(
                    user_id=owner,
                    filename="synthetic.pdf",
                    original_name="synthetic.pdf",
                    mime_type="application/pdf",
                    sha256_hash="a" * 64,
                    size_bytes=9,
                    storage_path="/test-fixture/legacy.pdf",
                    processing_method="legacy_ocr",
                    status="done",
                )
            )
            await db.commit()
    finally:
        await engine.dispose()


async def test_real_upgrade_preserves_rows_and_downgrade_refuses_import_data(
    owned_migration_database: MigrationDatabase,
) -> None:
    database = owned_migration_database
    await database.migrate("upgrade", "739144d5eaef")
    owner = uuid.uuid4()
    await database.connection.execute(
        "INSERT INTO users(id,email,password_hash,display_name,is_active) VALUES($1,'migration@example.test','synthetic-hash','Synthetic',true)",
        owner,
    )
    await seed_legacy_finance(database, owner)
    before = await snapshot(database)
    await database.migrate("upgrade", new_revision())
    assert await snapshot(database) == before
    assert await database.connection.fetchval("SELECT count(*) FROM bank_import_batches") == 0
    await database.migrate("downgrade", "739144d5eaef")
    assert await snapshot(database) == before
    await database.migrate("upgrade", new_revision())
    assert await snapshot(database) == before
    batch_id = uuid.uuid4()
    await database.connection.execute(
        "INSERT INTO bank_import_batches(id,user_id,kind) VALUES($1,$2,'statement')",
        batch_id,
        owner,
    )
    with pytest.raises(RuntimeError, match="Cannot downgrade.*bank import"):
        await database.migrate("downgrade", "739144d5eaef")
    assert await database.connection.fetchval("SELECT id FROM bank_import_batches") == batch_id
    assert await snapshot(database) == before
