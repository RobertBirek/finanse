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
from app.finance.schemas import AccountCreate
from tests.test_finance.test_loans import transfer


def test_loan_migration_is_the_single_head() -> None:
    backend = Path(__file__).resolve().parents[2]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["7f8ce92bda94"]
    assert scripts.get_revision("c2d7e9a4f801").down_revision == "b8e4c2f1a7d9"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_loan_migration_preserves_old_records(db_session: AsyncSession) -> None:
    backend = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "loan_migration", backend / "migrations/versions/c2d7e9a4f801_loan_schedules.py"
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    await db_session.execute(
        text(
            "INSERT INTO accounts (id,user_id,name,type,currency,source,is_active,is_budget_account) VALUES (:id,:owner,'Legacy','cash','PLN','manual',true,true)"
        ),
        {"id": uuid.uuid4(), "owner": uuid.uuid4()},
    )
    owner = uuid.uuid4()
    debt = await service.create_account(
        db_session, owner, AccountCreate(name="Old debt", type="credit")
    )
    payer = await service.create_account(
        db_session, owner, AccountCreate(name="Old payer", type="checking")
    )
    await transfer(db_session, owner, debt, payer, 12345)
    queries = [
        text(f"SELECT * FROM {table} ORDER BY id")
        for table in ("accounts", "financial_transactions", "postings", "actual_import_mappings")
    ]
    before = [(await db_session.execute(query)).all() for query in queries]
    connection = await db_session.connection()

    def migrate(sync: Connection) -> None:
        with Operations.context(MigrationContext.configure(sync)):
            migration.downgrade()
            migration.upgrade()

    await connection.run_sync(migrate)
    assert [(await db_session.execute(query)).all() for query in queries] == before
    assert await db_session.scalar(text("SELECT count(*) FROM loan_agreements")) == 0
