import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance import service
from app.finance.schemas import CategoryCreate, PostingCreate, TransactionCreate


def test_account_metadata_migration_extends_single_current_head() -> None:
    backend = Path(__file__).resolve().parents[2]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["b8e4c2f1a7d9"]
    revision = scripts.get_revision("b8e4c2f1a7d9")
    assert revision is not None
    assert revision.down_revision == "c7f8c620460d"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_metadata_migration_preserves_existing_account_and_ledger(
    db_session: AsyncSession,
) -> None:
    backend = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "account_metadata_migration",
        backend / "migrations/versions/b8e4c2f1a7d9_account_bank_metadata.py",
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    account_id, owner = uuid.uuid4(), uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO accounts (id, user_id, name, type, currency, source, is_active, is_budget_account) VALUES (:id, :owner, 'Legacy cash', 'cash', 'PLN', 'manual', true, true)"
        ),
        {"id": account_id, "owner": owner},
    )
    await db_session.commit()
    category = await service.create_category(
        db_session, owner, CategoryCreate(name="Legacy expense", type="expense")
    )
    await service.create_transaction(
        db_session,
        owner,
        TransactionCreate(
            description="Preserved ledger",
            type="expense",
            postings=[
                PostingCreate(
                    account_id=account_id, source_amount=123, base_amount_pln=123, direction="debit"
                ),
                PostingCreate(
                    category_id=category.id,
                    source_amount=123,
                    base_amount_pln=123,
                    direction="credit",
                ),
            ],
        ),
    )
    await db_session.commit()
    ledger_queries = [
        text("SELECT * FROM postings ORDER BY id"),
        text("SELECT * FROM financial_transactions ORDER BY id"),
    ]
    ledger_before = [(await db_session.execute(query)).all() for query in ledger_queries]
    snapshot_query = text(
        "SELECT id, user_id, name, type, currency, source, is_active, is_budget_account FROM accounts ORDER BY id"
    )
    before = (await db_session.execute(snapshot_query)).all()
    connection = await db_session.connection()

    def migrate(sync_connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(sync_connection)):
            migration.downgrade()
            migration.upgrade()

    await connection.run_sync(migrate)
    after = (await db_session.execute(snapshot_query)).all()
    assert before == after
    assert ledger_before == [(await db_session.execute(query)).all() for query in ledger_queries]
    row = (
        await db_session.execute(
            text("SELECT bank_name, account_holder, iban, bic, notes FROM accounts WHERE id=:id"),
            {"id": account_id},
        )
    ).one()
    assert tuple(row) == (None, None, None, None, None)
