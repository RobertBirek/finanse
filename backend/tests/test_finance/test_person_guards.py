"""Attribution cannot be invalidated through another finance editor."""

from datetime import date

import pytest

from app.finance import service
from app.finance.schemas import AccountCreate, AccountUpdate, TransactionUpdate
from tests.test_finance.test_people import gift, link, person

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("change", ["pending", "date", "delete"])
async def test_linked_gift_requires_unlink_before_identity_change(db_session, change):
    owner, txn, _, _ = await gift(db_session)
    p = await person(db_session, owner)
    await link(db_session, owner, txn.id, p.id)
    with pytest.raises(ValueError, match="person|osob"):
        if change == "delete":
            await service.delete_transaction(db_session, owner, txn.id)
        else:
            data = (
                TransactionUpdate(is_pending=True)
                if change == "pending"
                else TransactionUpdate(transaction_date=date(2026, 2, 1))
            )
            await service.update_transaction(db_session, owner, txn.id, data)


async def test_reference_does_not_retype_or_remove_existing_account(db_session):
    owner, _, _, _ = await gift(db_session)
    account = await service.create_account(
        db_session, owner, AccountCreate(name="Reference", type="checking", is_budget_account=False)
    )
    await person(db_session, owner, reference_account_id=account.id)
    with pytest.raises(ValueError, match="person|osob"):
        await service.update_account(
            db_session, owner, account.id, AccountUpdate(is_budget_account=True)
        )
    with pytest.raises(ValueError, match="person|osob"):
        await service.delete_account(db_session, owner, account.id)
    archived = await service.update_account(
        db_session, owner, account.id, AccountUpdate(is_active=False)
    )
    assert not archived.is_active


async def test_narrative_and_unlink_do_not_trap_manual_gift(db_session):
    from app.finance.people import unlink_gift
    from app.finance.person_context import get_person_link_context
    from app.finance.person_schemas import GiftUnlinkRequest

    owner, txn, _, _ = await gift(db_session)
    p = await person(db_session, owner)
    await link(db_session, owner, txn.id, p.id)
    edited = await service.update_transaction(
        db_session, owner, txn.id, TransactionUpdate(description="My description")
    )
    assert edited.description == "My description"
    ctx = await get_person_link_context(db_session, owner, txn.id)
    await unlink_gift(
        db_session,
        owner,
        txn.id,
        GiftUnlinkRequest(expected_transaction_snapshot=ctx.snapshot),
        idempotency_key="unlink",
    )
    await service.update_transaction(db_session, owner, txn.id, TransactionUpdate(is_pending=True))
    assert txn.is_pending


@pytest.mark.parametrize("change", ["date", "delete", "budget", "archive"])
async def test_waiting_mutations_observe_committed_person_state(db_session, test_database, change):
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.finance.people import update_person
    from app.finance.person_schemas import PersonUpdate

    owner, txn, _, _ = await gift(db_session)
    ref = await service.create_account(
        db_session, owner, AccountCreate(name="Ref", type="checking", is_budget_account=False)
    )
    p = await person(db_session, owner, reference_account_id=ref.id)
    txn_id, ref_id = txn.id, ref.id
    await db_session.commit()
    # The first operation holds the existing owner mutation lock until commit.
    if change == "archive":
        await update_person(
            db_session, owner, p.id, PersonUpdate(expected_version=1, is_active=False)
        )
    else:
        await link(db_session, owner, txn_id, p.id)
    entered = asyncio.Event()
    factory = async_sessionmaker(test_database, expire_on_commit=False)

    async def waiting():
        async with factory() as db:
            entered.set()
            try:
                if change == "date":
                    await service.update_transaction(
                        db, owner, txn_id, TransactionUpdate(transaction_date=date(2026, 3, 1))
                    )
                elif change == "delete":
                    await service.delete_transaction(db, owner, txn_id)
                elif change == "budget":
                    await service.update_account(
                        db, owner, ref_id, AccountUpdate(is_budget_account=True)
                    )
                else:
                    await link(db, owner, txn_id, p.id)
                await db.commit()
                return None
            except ValueError as error:
                await db.rollback()
                return error

    task = asyncio.create_task(waiting())
    await asyncio.wait_for(entered.wait(), 10)
    await db_session.commit()
    result = await asyncio.wait_for(task, 15)
    assert isinstance(result, ValueError)


async def test_linked_gift_blocks_currency_correction_without_changing_money(
    db_session, monkeypatch
):
    from app.finance.currency_correction import apply_correction, preview_correction
    from app.finance.nbp_rates import NbpRateProvider
    from app.finance.person_reads import get_person_summary
    from tests.test_finance.test_currency_correction import Rates
    from tests.test_finance.test_people import ledger

    monkeypatch.setattr(NbpRateProvider, "get_rate", Rates.get_rate)
    owner, txn, bank, _ = await gift(db_session)
    bank.source = "actual"
    txn.source = "actual"
    await db_session.commit()
    bank_id, txn_id = bank.id, txn.id
    # The correction can have been approved BEFORE the gift attribution.
    plan = await preview_correction(db_session, owner, bank_id, Rates())
    p = await person(db_session, owner)
    await link(db_session, owner, txn_id, p.id)
    before = await ledger(db_session)
    summary = await get_person_summary(db_session, owner, p.id)
    with pytest.raises(ValueError, match="osob"):
        await apply_correction(db_session, owner, plan, approved_digest=plan.digest())
    assert await ledger(db_session) == before
    assert (await service.get_account(db_session, owner, bank_id)).currency == "PLN"
    assert await get_person_summary(db_session, owner, p.id) == summary
