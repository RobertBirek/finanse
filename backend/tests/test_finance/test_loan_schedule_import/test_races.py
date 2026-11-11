import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.finance.imports.errors import ImportError
from app.finance.loan_schedule_models import LoanScheduleRevision
from tests.test_finance.test_loan_schedule_import.activation_fixtures import confirmed_case

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("same_key", [True, False])
async def test_two_real_sessions_activate_only_one_intent(
    db_session, test_database, owner, tmp_path, monkeypatch, same_key
):
    from app.finance.loan_schedule_commands import activate_schedule

    case, _preview, request = await confirmed_case(db_session, owner.id, tmp_path, monkeypatch)
    owner_id, batch_id = owner.id, case.batch.id
    await db_session.commit()
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    start = asyncio.Event()

    async def attempt(key):
        async with sessions() as db:
            await start.wait()
            try:
                result = await activate_schedule(db, owner_id, batch_id, request, key)
                await db.commit()
                return result
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
        assert sum(isinstance(r, ImportError) for r in results) == 1
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(LoanScheduleRevision)
            .where(LoanScheduleRevision.state == "active")
        )
        == 1
    )


async def test_payment_committed_in_separate_session_after_preview_invalidates_activation(
    db_session, test_database, owner, tmp_path, monkeypatch
):
    from app.finance import loans
    from app.finance.loan_schedule_commands import activate_schedule
    from tests.test_finance.test_loan_schedule_import.factories import payment_transfer

    case, _preview, request = await confirmed_case(db_session, owner.id, tmp_path, monkeypatch)
    transaction = await payment_transfer(db_session, owner.id, case.loan)
    owner_id, batch_id, loan_id, item_id, tx_id = (
        owner.id,
        case.batch.id,
        case.loan.id,
        case.installment.id,
        transaction.id,
    )
    await db_session.commit()
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    async with sessions() as manual:
        await loans.link_loan_payment(manual, owner_id, loan_id, item_id, tx_id)
        await manual.commit()
    async with sessions() as command:
        with pytest.raises(ImportError):
            await activate_schedule(command, owner_id, batch_id, request, "stale-after-payment")
    assert await db_session.scalar(select(func.count()).select_from(LoanScheduleRevision)) == 0


async def test_two_distinct_batches_cannot_activate_against_same_old_loan_snapshot(
    db_session, test_database, owner, tmp_path, monkeypatch
):
    from app.finance.loan_schedule_commands import activate_schedule
    from app.finance.loan_schedule_preview import prepare_schedule_preview
    from app.finance.loan_schedule_schemas import ScheduleActivateRequest
    from tests.test_finance.test_loan_schedule_import.activation_fixtures import schedule_case

    first, _preview, request = await confirmed_case(db_session, owner.id, tmp_path, monkeypatch)
    second = await schedule_case(db_session, owner.id, tmp_path, monkeypatch)
    second_request = second.request.model_copy(update={"target": first.request.target})
    second_preview = await prepare_schedule_preview(
        db_session, owner.id, second.batch.id, second_request
    )
    requests = [
        (first.batch.id, request),
        (
            second.batch.id,
            ScheduleActivateRequest(
                preview_id=second_preview.id, request_hash=second_preview.request_hash
            ),
        ),
    ]
    owner_id = owner.id
    await db_session.commit()
    sessions = async_sessionmaker(test_database, expire_on_commit=False)

    async def attempt(batch_id, body, key):
        async with sessions() as db:
            try:
                result = await activate_schedule(db, owner_id, batch_id, body, key)
                await db.commit()
                return result
            except ImportError as error:
                await db.rollback()
                return error

    results = await asyncio.wait_for(
        asyncio.gather(
            *(
                attempt(batch, body, f"different-batch-{i}")
                for i, (batch, body) in enumerate(requests)
            )
        ),
        30,
    )
    assert sum(isinstance(r, ImportError) for r in results) == 1
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(LoanScheduleRevision)
            .where(LoanScheduleRevision.state == "active")
        )
        == 1
    )
