"""BO edit and first posting must serialize on real database connections."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.finance import service
from tests.test_finance.test_opening_balance_guards import transfer
from tests.test_finance.test_opening_balances import DAY, opening_account, owner_record

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("opening_first", [True, False])
async def test_first_posting_races_opening_edit(db_session, opening_first):
    from app.finance.opening_balance_schemas import OpeningBalanceUpdate
    from app.finance.opening_balances import update_opening_balance

    owner = await owner_record(db_session)
    account = await opening_account(db_session, owner)
    payer = await opening_account(db_session, owner)
    account_id = account.id
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    ready, release, attempting = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def edit(db):
        return await update_opening_balance(
            db,
            owner,
            account_id,
            OpeningBalanceUpdate(amount_minor=7500, date=DAY, expected_version=1),
            "race",
        )

    async def first():
        async with sessions() as db, db.begin():
            if opening_first:
                await edit(db)
            else:
                await transfer(db, owner, account, payer)
            ready.set()
            await release.wait()

    async def second():
        async with sessions() as db, db.begin():
            attempting.set()
            if opening_first:
                return await transfer(db, owner, account, payer)
            return await edit(db)

    first_task = asyncio.create_task(first())
    second_task = None
    try:
        await asyncio.wait_for(ready.wait(), timeout=10)
        second_task = asyncio.create_task(second())
        await asyncio.wait_for(attempting.wait(), timeout=10)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(second_task), timeout=0.3)
        release.set()
        await asyncio.wait_for(first_task, timeout=10)
        if opening_first:
            await asyncio.wait_for(second_task, timeout=10)
        else:
            with pytest.raises(ValueError, match="transakc"):
                await asyncio.wait_for(second_task, timeout=10)
        async with sessions() as db:
            actual = await service.get_account(db, owner, account_id)
            assert actual.opening_balance.amount_minor == (7500 if opening_first else 0)
            assert not actual.opening_balance.can_edit
            assert actual.balance_pln == (7400 if opening_first else -100)
    finally:
        release.set()
        tasks = [first_task, *([second_task] if second_task is not None else [])]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
