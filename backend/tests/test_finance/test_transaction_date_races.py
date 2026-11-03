import asyncio
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit.models import AuditEvent
from app.finance.document_guards import lock_document_mutations
from app.finance.models import TransactionDateMetadata
from app.finance.schemas import TransactionDatesUpdate
from app.finance.transaction_dates import TransactionDateError, set_transaction_dates
from app.finance.transactions import delete_transaction
from tests.test_finance.test_bill_payments import create_owner
from tests.test_finance.test_transaction_search import seed

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("second_operation", ["edit", "delete"])
async def test_date_edit_serializes_with_concurrent_edit_or_delete(db_session, second_operation):
    owner = await create_owner(db_session)
    txn, _, _ = await seed(db_session, owner, day=date(2026, 2, 2))
    data = TransactionDatesUpdate(
        purchase_date=date(2026, 1, 30),
        booking_date=date(2026, 2, 2),
        expected_version=0,
        expected_updated_at=txn.updated_at,
    )
    txn_id = txn.id
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    admitted = asyncio.Event()
    release = asyncio.Event()
    second_started = asyncio.Event()

    async def first():
        async with sessions() as session, session.begin():
            await lock_document_mutations(session, owner)
            result = await set_transaction_dates(session, owner, txn_id, data)
            assert result.date_metadata.version == 1
            admitted.set()
            await release.wait()

    async def second():
        await admitted.wait()
        async with sessions() as session, session.begin():
            second_started.set()
            if second_operation == "edit":
                with pytest.raises(TransactionDateError, match="zmieniły"):
                    await set_transaction_dates(session, owner, txn_id, data)
            else:
                assert await delete_transaction(session, owner, txn_id)

    task1 = asyncio.create_task(first())
    task2 = asyncio.create_task(second())
    try:
        await asyncio.wait_for(second_started.wait(), 10)
        assert not task2.done()
    finally:
        release.set()
    await asyncio.wait_for(asyncio.gather(task1, task2), 15)
    assert await db_session.scalar(select(func.count()).select_from(TransactionDateMetadata)) == (
        1 if second_operation == "edit" else 0
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "set_transaction_dates")
        )
        == 1
    )
