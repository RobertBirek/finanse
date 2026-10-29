import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.finance.bill_payments import allocate_payment
from app.finance.bills_schemas import AllocationCreate, MutationContext
from app.finance.models import DocumentPaymentAllocation
from tests.test_finance.test_bill_payments import create_owner, expense, setup_bill

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_two_real_sessions_cannot_overallocate_a_posting(db_session) -> None:
    owner = await create_owner(db_session)
    first_bill = await setup_bill(db_session, owner, 5_000)
    second_bill = await setup_bill(db_session, owner, 5_000)
    posting_id, _, _ = await expense(db_session, owner, 7_000)
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def allocate(bill_id, key):
        async with sessions() as session:
            try:
                response = await allocate_payment(
                    session,
                    owner,
                    bill_id,
                    AllocationCreate(version=2, posting_id=posting_id, amount_minor=5_000),
                    context=MutationContext(idempotency_key=key),
                )
                await session.commit()
                return response
            except (LookupError, RuntimeError, ValueError) as error:
                await session.rollback()
                return error

    one, two = await asyncio.wait_for(
        asyncio.gather(allocate(first_bill.id, "first"), allocate(second_bill.id, "second")),
        timeout=10,
    )
    assert sum(not isinstance(item, Exception) for item in (one, two)) == 1
    assert isinstance(one, Exception) or isinstance(two, Exception)
    assert (
        await db_session.scalar(
            select(func.sum(DocumentPaymentAllocation.amount_minor)).where(
                DocumentPaymentAllocation.posting_id == posting_id
            )
        )
        <= 7_000
    )
