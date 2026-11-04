"""Lock admission determines the decision, never stale in-memory authority."""

import asyncio
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.finance.rule_events import apply_rule_event, claim_rule_event
from app.finance.rule_models import TransactionCategorizationRule as Rule
from app.finance.rule_policy import command
from tests.test_finance.test_categorization_races import wait_for_database_lock
from tests.test_finance.test_rule_events import event_for, new_expense, ready

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("first_operation", ["worker", "pause"])
async def test_rule_pause_serializes_with_job_decision(db_session, first_operation):
    owner, _, _, _, _, rule, txn = await ready(db_session)
    event = await event_for(db_session, txn)
    lease = await claim_rule_event(db_session, event.id)
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    admitted = asyncio.Event()
    release = asyncio.Event()
    second_ready = asyncio.Event()
    pids = []
    outcomes = []

    async def operation(db, what):
        if what == "worker":
            outcomes.append(await apply_rule_event(db, lease))
        else:
            await command(
                db,
                owner,
                "rule_pause",
                {"expected_version": rule["version"]},
                "pause-race",
                uuid.UUID(rule["id"]),
            )

    async def first():
        async with sessions() as db, db.begin():
            await operation(db, first_operation)
            admitted.set()
            await release.wait()

    async def second():
        await admitted.wait()
        async with sessions() as db, db.begin():
            pids.append(await db.scalar(text("SELECT pg_backend_pid()")))
            second_ready.set()
            await operation(db, "pause" if first_operation == "worker" else "worker")

    a = asyncio.create_task(first())
    b = asyncio.create_task(second())
    try:
        await asyncio.wait_for(second_ready.wait(), 10)
        await wait_for_database_lock(db_session, pids[0])
        assert not b.done()
    finally:
        release.set()
        results = await asyncio.wait_for(asyncio.gather(a, b, return_exceptions=True), 15)
    assert not any(isinstance(r, BaseException) for r in results), results
    assert outcomes == (["applied"] if first_operation == "worker" else ["skipped"])


async def test_creation_enrollment_has_no_implicit_rule_fk_lock(db_session):
    owner, _, account, marker, _, rule, _ = await ready(db_session)
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as held:
        await held.scalar(select(Rule).where(Rule.id == uuid.UUID(rule["id"])).with_for_update())
        async with sessions() as source:
            created = await asyncio.wait_for(new_expense(source, owner, account, marker), 5)
            await source.commit()
            event = await event_for(source, created)
            assert event.status == "ready" and str(event.observed_rule_id) == rule["id"]
        await held.rollback()
