import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND = Path(__file__).parents[2]
TEST_DATABASE_URL = "postgresql+asyncpg://finanse:finanse@127.0.0.1:5432/finanse_test"
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


def run_alembic(*args: str) -> None:
    environment = os.environ | {"DATABASE_URL": TEST_DATABASE_URL}
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


async def reset_disposable_schema() -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
            await connection.execute(text("GRANT ALL ON SCHEMA public TO finanse"))
    finally:
        await engine.dispose()


async def query_scalar(statement: str) -> object:
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect() as connection:
            return (await connection.execute(text(statement))).scalar_one()
    finally:
        await engine.dispose()


async def query_strings(statement: str) -> set[str]:
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect() as connection:
            return set((await connection.execute(text(statement))).scalars())
    finally:
        await engine.dispose()


@pytest.mark.integration
def test_migration_preserves_old_rows_without_backfill() -> None:
    asyncio.run(reset_disposable_schema())
    run_alembic("upgrade", PREVIOUS_REVISION)
    asyncio.run(insert_synthetic_account())

    run_alembic("upgrade", CURRENT_REVISION)

    assert asyncio.run(existing_account_name()) == "synthetic-preservation-row"
    assert asyncio.run(public_tables()) >= NEW_TABLES
    assert REQUIRED_CONSTRAINTS <= asyncio.run(financial_document_constraints())

    run_alembic("downgrade", PREVIOUS_REVISION)
    assert asyncio.run(public_tables()).isdisjoint(NEW_TABLES)
    assert asyncio.run(existing_account_name()) == "synthetic-preservation-row"

    run_alembic("upgrade", CURRENT_REVISION)
    assert asyncio.run(public_tables()) >= NEW_TABLES
    assert asyncio.run(existing_account_name()) == "synthetic-preservation-row"


async def insert_synthetic_account() -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO accounts "
                    "(id, user_id, name, type, currency, source, is_active, is_budget_account, "
                    "opened_at, created_at, updated_at) "
                    "VALUES ('00000000-0000-0000-0000-000000000001', "
                    "'00000000-0000-0000-0000-000000000002', 'synthetic-preservation-row', "
                    "'checking', 'PLN', 'manual', true, true, CURRENT_DATE, now(), now())"
                )
            )
    finally:
        await engine.dispose()


async def existing_account_name() -> str:
    return str(
        await query_scalar(
            "SELECT name FROM accounts WHERE id = '00000000-0000-0000-0000-000000000001'"
        )
    )


async def public_tables() -> set[str]:
    return await query_strings("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")


async def financial_document_constraints() -> set[str]:
    return await query_strings(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid IN ("
        "'financial_documents'::regclass, 'financial_document_sources'::regclass, "
        "'document_payment_allocations'::regclass, 'recurring_occurrence_coverages'::regclass, "
        "'document_extraction_revisions'::regclass)"
    )
