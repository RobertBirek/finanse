import asyncio
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.finance.imports.commit import commit_import
from app.finance.imports.errors import ImportError
from app.finance.models import FinanceCommandReceipt, FinancialTransaction
from tests.test_finance.test_bank_imports.commit_fixtures import confirmed_import

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("same_key", [True, False])
async def test_two_real_sessions_commit_one_intent_only_once(
    db_session, test_database, owner, tmp_path, monkeypatch, same_key
):
    case, request = await confirmed_import(db_session, owner.id, tmp_path, monkeypatch)
    owner_id, batch_id = owner.id, case.batch_id
    await db_session.commit()
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    start = asyncio.Event()

    async def attempt(key):
        async with sessions() as db:
            await start.wait()
            try:
                response = await commit_import(db, owner_id, batch_id, request, key)
                await db.commit()
                return response
            except ImportError as error:
                await db.rollback()
                return error

    tasks = [
        asyncio.create_task(attempt(key))
        for key in ["race-one", "race-one" if same_key else "race-two"]
    ]
    start.set()
    results = await asyncio.wait_for(asyncio.gather(*tasks), 30)
    if same_key:
        assert results[0] == results[1] and not isinstance(results[0], ImportError)
    else:
        failures = [result for result in results if isinstance(result, ImportError)]
        assert len(failures) == 1 and failures[0].code == "preview_stale"
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 1
    assert await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 1


async def test_two_batches_cannot_create_same_strong_reference_on_one_account(
    db_session, test_database, owner, tmp_path, monkeypatch
):
    from app.finance.imports.decisions import save_decisions
    from app.finance.imports.preview import prepare_preview
    from app.finance.imports.schemas import (
        CommitRequest,
        DecisionUpdate,
        ImportDecisionInput,
        PreviewRequest,
    )
    from app.finance.imports.service import create_batch
    from tests.test_finance.test_bank_imports.review_fixtures import additional_source
    from tests.test_finance.test_bank_imports.test_contracts import parsed_statement, statement_row

    payload = parsed_statement(
        account_reference=None, rows=[statement_row(bank_reference="real-identity")]
    )
    case, request = await confirmed_import(db_session, owner.id, tmp_path, monkeypatch, payload)
    other = await create_batch(db_session, owner.id, "statement")
    source, rows = await additional_source(db_session, owner.id, other.id, tmp_path, payload)
    decision = ImportDecisionInput(
        group_id=uuid.uuid4(),
        row_ids=[rows[0].id],
        action="create",
        kind="expense",
        account_id=case.account.id,
        category_id=case.category.id,
    )
    batch = await save_decisions(
        db_session, owner.id, other.id, DecisionUpdate(expected_version=1, decisions=[decision])
    )
    preview = await prepare_preview(
        db_session,
        owner.id,
        batch.id,
        PreviewRequest(
            expected_version=batch.version,
            group_ids=[decision.group_id],
            acknowledgements=[f"opening_gap:{source.id}"],
        ),
    )
    owner_id, first_batch, second_batch = owner.id, case.batch_id, batch.id
    await db_session.commit()
    sessions = async_sessionmaker(test_database, expire_on_commit=False)

    async def attempt(batch_id, body, key):
        async with sessions() as db:
            try:
                result = await commit_import(db, owner_id, batch_id, body, key)
                await db.commit()
                return result
            except ImportError as error:
                await db.rollback()
                return error

    results = await asyncio.wait_for(
        asyncio.gather(
            attempt(first_batch, request, "first-batch"),
            attempt(
                second_batch,
                CommitRequest(preview_id=preview.id, request_hash=preview.request_hash),
                "second-batch",
            ),
        ),
        30,
    )
    assert sum(not isinstance(result, ImportError) for result in results) == 1
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 1
    assert await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 1


async def test_commit_rechecks_preview_after_waiting_for_a_manual_account_writer(
    db_session, test_database, owner, tmp_path, monkeypatch
):
    from sqlalchemy import text

    from app.finance.schemas import PostingCreate, TransactionCreate
    from app.finance.transactions import create_transaction
    from tests.test_finance.test_categorization_races import wait_for_database_lock

    case, request = await confirmed_import(db_session, owner.id, tmp_path, monkeypatch)
    owner_id, batch_id, account_id, category_id = (
        owner.id,
        case.batch_id,
        case.account.id,
        case.category.id,
    )
    await db_session.commit()
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    async with sessions() as manual:
        # This takes the existing core's FOR SHARE account lock until commit.
        await create_transaction(
            manual,
            owner_id,
            TransactionCreate(
                transaction_date="2026-01-03",
                description="Concurrent manual purchase",
                type="expense",
                postings=[
                    PostingCreate(
                        account_id=account_id,
                        source_amount=100,
                        base_amount_pln=100,
                        direction="debit",
                    ),
                    PostingCreate(
                        category_id=category_id,
                        source_amount=100,
                        base_amount_pln=100,
                        direction="credit",
                    ),
                ],
            ),
        )
        pids = []
        ready = asyncio.Event()

        async def import_attempt():
            async with sessions() as db:
                pids.append(await db.scalar(text("select pg_backend_pid()")))
                ready.set()
                try:
                    await commit_import(db, owner_id, batch_id, request, "wait-for-manual")
                except ImportError as error:
                    await db.rollback()
                    return error
                await db.commit()
                return None

        task = asyncio.create_task(import_attempt())
        try:
            await asyncio.wait_for(ready.wait(), 10)
            await wait_for_database_lock(db_session, pids[0])
        finally:
            await manual.commit()
        result = await asyncio.wait_for(task, 30)
    assert result is not None and result.code == "preview_stale"
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 1
    assert await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 0
