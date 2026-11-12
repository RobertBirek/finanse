import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.finance.annotation_models import FinanceTag
from app.finance.annotation_schemas import AnnotationUpdate
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_annotations import context, edit
from tests.test_finance.test_categorization import setup
from tests.test_finance.test_transaction_search import seed

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_parallel_first_annotations_only_one_wins(db_session):
    owner, txn, _, _, _ = await setup(db_session)
    txn_id = txn.id
    async with client_for(db_session, owner) as client:
        data = AnnotationUpdate(**edit(await context(client, txn), note="Winner"))
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    from app.finance.annotations import AnnotationError, update_annotations

    async def approve(key):
        async with sessions() as db:
            try:
                result = await update_annotations(db, owner, txn_id, data, idempotency_key=key)
                await db.commit()
                return result
            except AnnotationError:
                await db.rollback()
                return None

    results = await asyncio.wait_for(asyncio.gather(approve("one"), approve("two")), 20)
    assert sum(r is not None for r in results) == 1


async def test_concurrent_normalized_tag_creation_reuses_one_id(db_session):
    owner, first, _, _, _ = await setup(db_session)
    second, *_ = await seed(db_session, owner)
    async with client_for(db_session, owner) as client:
        requests = [
            (txn.id, AnnotationUpdate(**edit(await context(client, txn), tags=[name])))
            for txn, name in [(first, "Remont"), (second, "remont")]
        ]
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    from app.finance.annotations import update_annotations

    async def approve(txn_id, data):
        async with sessions() as db:
            result = await update_annotations(db, owner, txn_id, data, idempotency_key=str(txn_id))
            await db.commit()
            return result

    results = await asyncio.wait_for(asyncio.gather(*(approve(*p) for p in requests)), 20)
    assert results[0].tags[0].id == results[1].tags[0].id
    assert await db_session.scalar(select(func.count()).select_from(FinanceTag)) == 1
