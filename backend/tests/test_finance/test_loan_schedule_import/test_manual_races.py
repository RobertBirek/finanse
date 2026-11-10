import asyncio

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.finance import loans
from app.finance.document_guards import lock_document_mutations
from app.finance.loan_schemas import LoanInstallmentUpdate
from app.finance.models import LoanPaymentLink
from tests.test_finance.test_categorization_races import wait_for_database_lock
from tests.test_finance.test_loan_schedule_import.factories import legacy_loan, payment_transfer

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("operation", ["update", "delete", "link", "unlink"])
async def test_manual_mutation_waits_for_owner_mutex_before_taking_loan_rows(
    db_session, test_database, owner, operation
):
    loan, item, _ = await legacy_loan(db_session, owner.id)
    transaction = await payment_transfer(db_session, owner.id, loan)
    link_id = None
    if operation == "unlink":
        await loans.link_loan_payment(db_session, owner.id, loan.id, item.id, transaction.id)
        link_id = await db_session.scalar(
            select(LoanPaymentLink.id).where(LoanPaymentLink.installment_id == item.id)
        )
    owner_id, loan_id, item_id, transaction_id = owner.id, loan.id, item.id, transaction.id
    await db_session.commit()
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    ready = asyncio.Event()
    pids = []

    async def mutate():
        async with sessions() as db:
            pids.append(await db.scalar(text("SELECT pg_backend_pid()")))
            ready.set()
            if operation == "update":
                await loans.update_loan_installment(
                    db, owner_id, loan_id, item_id, LoanInstallmentUpdate(interest_pln=600)
                )
            elif operation == "delete":
                await loans.delete_loan_installment(db, owner_id, loan_id, item_id)
            elif operation == "link":
                await loans.link_loan_payment(db, owner_id, loan_id, item_id, transaction_id)
            else:
                await loans.unlink_loan_payment(db, owner_id, loan_id, link_id)
            await db.commit()

    async with sessions() as holder:
        await lock_document_mutations(holder, owner_id)
        task = asyncio.create_task(mutate())
        try:
            await asyncio.wait_for(ready.wait(), 10)
            await wait_for_database_lock(db_session, pids[0])
            assert not task.done()
            # If the waiter took loan first, this NOWAIT would fail (AB/BA deadlock).
            await holder.execute(
                text("SELECT id FROM loan_agreements WHERE id=:id FOR UPDATE NOWAIT"),
                {"id": loan_id},
            )
            await holder.commit()
            await asyncio.wait_for(task, 30)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
