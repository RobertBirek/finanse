import asyncio

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.finance.categorization import apply_categorization
from app.finance.categorization_context import CategorizationError
from app.finance.categorization_schemas import CategorizationApply
from app.finance.entities import delete_category
from app.finance.models import Category, Posting, TransactionCategorizationState
from app.finance.transactions import delete_transaction
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_categorization import preview, setup

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("first_operation", ["categorization", "account_update"])
async def test_account_updates_serialize_with_reviewed_account_snapshot(
    db_session, first_operation
):
    from app.finance.entities import update_account
    from app.finance.schemas import AccountUpdate

    owner, txn, account, _, home = await setup(db_session)
    txn_id = txn.id
    account_id = account.id
    async with client_for(db_session, owner) as client:
        p = await preview(client, txn, [{"category_id": str(home.id), "amount_minor": 10000}])
    await db_session.commit()
    data = CategorizationApply(
        expected_version=p["expected_version"],
        expected_preview_snapshot=p["preview_snapshot"],
        parts=p["after_parts"],
        confirmed=True,
    )
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    admitted = asyncio.Event()
    release = asyncio.Event()
    second_ready = asyncio.Event()
    pid_box = []

    async def first():
        async with sessions() as db, db.begin():
            if first_operation == "categorization":
                await apply_categorization(
                    db, owner, txn_id, data, idempotency_key="account-race-first"
                )
            else:
                await update_account(db, owner, account_id, AccountUpdate(is_budget_account=False))
            admitted.set()
            await release.wait()

    async def second():
        await admitted.wait()
        async with sessions() as db, db.begin():
            pid_box.append(await db.scalar(text("SELECT pg_backend_pid()")))
            second_ready.set()
            if first_operation == "categorization":
                await update_account(db, owner, account_id, AccountUpdate(is_budget_account=False))
            else:
                with pytest.raises(CategorizationError, match="zmieniły"):
                    await apply_categorization(
                        db, owner, txn_id, data, idempotency_key="account-race-second"
                    )

    task1 = asyncio.create_task(first())
    task2 = asyncio.create_task(second())

    async def wait_for_serialization():
        while True:
            if task2.done():
                raise AssertionError("Concurrent operation bypassed the reviewed account snapshot")
            if await db_session.scalar(
                text("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid"),
                {"pid": pid_box[0]},
            ):
                return
            await asyncio.sleep(0.01)

    try:
        await asyncio.wait_for(second_ready.wait(), 10)
        await asyncio.wait_for(wait_for_serialization(), 10)
    finally:
        release.set()
        results = await asyncio.wait_for(asyncio.gather(task1, task2, return_exceptions=True), 15)
    assert not any(isinstance(result, BaseException) for result in results), results
    async with sessions() as db:
        assert await db.scalar(
            select(func.count()).select_from(TransactionCategorizationState)
        ) == (1 if first_operation == "categorization" else 0)


async def wait_for_database_lock(db, pid):
    async def waiting():
        while not await db.scalar(
            text("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid"), {"pid": pid}
        ):
            await asyncio.sleep(0.01)

    await asyncio.wait_for(waiting(), 10)


@pytest.mark.parametrize("second", ["approval", "delete", "category_delete"])
async def test_parallel_commands_preserve_identity_and_observe_new_category_usage(
    db_session, second
):
    owner, txn, _, _food, home = await setup(db_session)
    txn_id = txn.id
    home_id = home.id
    async with client_for(db_session, owner) as client:
        p = await preview(client, txn, [{"category_id": str(home_id), "amount_minor": 10000}])
    await db_session.commit()
    data = CategorizationApply(
        expected_version=p["expected_version"],
        expected_preview_snapshot=p["preview_snapshot"],
        parts=p["after_parts"],
        confirmed=True,
    )
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    admitted = asyncio.Event()
    release = asyncio.Event()
    second_ready = asyncio.Event()
    pid_box = []

    async def first():
        async with sessions() as db, db.begin():
            await apply_categorization(db, owner, txn_id, data, idempotency_key="first")
            admitted.set()
            await release.wait()

    async def concurrent():
        await admitted.wait()
        async with sessions() as db, db.begin():
            pid_box.append(await db.scalar(text("SELECT pg_backend_pid()")))
            second_ready.set()
            if second == "approval":
                with pytest.raises(CategorizationError, match="zmieniły"):
                    await apply_categorization(db, owner, txn_id, data, idempotency_key="second")
            elif second == "delete":
                assert await delete_transaction(db, owner, txn_id)
            else:
                with pytest.raises(ValueError, match="records"):
                    await delete_category(db, owner, home_id)

    task1 = asyncio.create_task(first())
    task2 = asyncio.create_task(concurrent())
    try:
        await asyncio.wait_for(second_ready.wait(), 10)
        await wait_for_database_lock(db_session, pid_box[0])
    finally:
        release.set()
    await asyncio.wait_for(asyncio.gather(task1, task2), 15)
    async with sessions() as db:
        assert await db.scalar(
            select(func.count()).select_from(TransactionCategorizationState)
        ) == (0 if second == "delete" else 1)
        if second != "delete":
            assert await db.get(Category, home_id) is not None
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(Posting)
                    .where(Posting.transaction_id == txn_id, Posting.category_id == home_id)
                )
                == 1
            )
