"""Quota counts potential paid calls, not guessed billing or model confidence."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.finance.suggestion_models import (
    CategorizationSuggestionJob as Job,
)
from tests.test_finance.test_rule_events import new_expense
from tests.test_finance.test_suggestion_jobs import job_for, suggestion_ready

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def prepared(db, job):
    from app.finance.suggestion_jobs import claim_suggestion_job, prepare_suggestion_job

    lease = await claim_suggestion_job(db, job.id)
    await db.commit()
    assert lease
    packet = await prepare_suggestion_job(db, lease)
    await db.commit()
    assert packet
    return lease, packet


async def test_last_daily_slot_is_serialized_and_excess_never_gets_next_day_backlog(
    db_session, monkeypatch
):
    from app.finance.suggestion_usage import reserve_suggestion_call

    monkeypatch.setattr(settings, "FINANCE_SUGGESTIONS_DAILY_CALL_LIMIT", 1)
    owner, _, account, marker, _, txn = await suggestion_ready(db_session, monkeypatch)
    second = await new_expense(db_session, owner, account, marker, "Second")
    await db_session.commit()
    a = await prepared(db_session, await job_for(db_session, txn))
    b = await prepared(db_session, await job_for(db_session, second))
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)

    async def reserve(args):
        async with sessions() as db:
            result = await reserve_suggestion_call(db, *args)
            await db.commit()
            return result

    results = await asyncio.wait_for(asyncio.gather(reserve(a), reserve(b)), 15)
    assert sum(r is not None for r in results) == 1
    jobs = (
        await db_session.scalars(
            select(Job).order_by(Job.id).execution_options(populate_existing=True)
        )
    ).all()
    assert sorted(j.status for j in jobs) == ["cancelled", "reserved"]
    loser = next(j for j in jobs if j.status == "cancelled")
    assert loser.reason_code == "quota_exceeded" and loser.next_attempt_at is None


async def test_reservation_replay_stolen_lease_and_nosend_release_are_version_fenced(
    db_session, monkeypatch
):
    from app.finance.suggestion_jobs import claim_suggestion_job
    from app.finance.suggestion_usage import release_nosend_reservation, reserve_suggestion_call

    _, _, _, _, _, txn = await suggestion_ready(db_session, monkeypatch)
    job = await job_for(db_session, txn)
    lease, packet = await prepared(db_session, job)
    r = await reserve_suggestion_call(db_session, lease, packet)
    await db_session.commit()
    first_id, first_version = r.id, r.reservation_version
    again = await reserve_suggestion_call(db_session, lease, packet)
    assert again.id == first_id and again.reservation_version == first_version
    await db_session.refresh(job)
    job.lease_deadline = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    successor = await claim_suggestion_job(db_session, job.id)
    await db_session.commit()
    r2 = await reserve_suggestion_call(db_session, successor, packet)
    await db_session.commit()
    assert r2.id == first_id and r2.reservation_version > first_version
    assert not await release_nosend_reservation(
        db_session, lease, first_id, first_version, reason="stale"
    )
    assert await release_nosend_reservation(
        db_session, successor, r2.id, r2.reservation_version, reason="nosend"
    )
    assert not await release_nosend_reservation(
        db_session, successor, r2.id, r2.reservation_version, reason="nosend"
    )


async def test_admitted_crash_never_retries_and_late_usage_only_updates_accounting(
    db_session, monkeypatch
):
    from app.finance.suggestion_client import ProviderOutcome, ProviderUsage
    from app.finance.suggestion_jobs import (
        admit_suggestion_dispatch,
        claim_suggestion_job,
        finish_suggestion_job,
        recover_suggestion_jobs,
    )
    from app.finance.suggestion_models import CategorizationProposalItem as Item
    from app.finance.suggestion_usage import (
        record_suggestion_usage,
        release_nosend_reservation,
        reserve_suggestion_call,
    )

    _, _, _, _, _, txn = await suggestion_ready(db_session, monkeypatch)
    job = await job_for(db_session, txn)
    lease, packet = await prepared(db_session, job)
    r = await reserve_suggestion_call(db_session, lease, packet)
    await db_session.commit()
    ticket = await admit_suggestion_dispatch(db_session, lease, r.reservation_version)
    await db_session.commit()
    assert ticket
    assert not await release_nosend_reservation(
        db_session, lease, r.id, r.reservation_version, reason="dispatched"
    )
    job.lease_deadline = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    await recover_suggestion_jobs(db_session, datetime.now(UTC))
    await db_session.commit()
    assert await claim_suggestion_job(db_session, job.id) is None
    usage = ProviderUsage(100, 20, "b" * 64)
    await record_suggestion_usage(db_session, ticket, usage)
    await record_suggestion_usage(db_session, ticket, usage)
    await db_session.commit()
    assert (
        await finish_suggestion_job(
            db_session, ticket, ProviderOutcome(None, usage, "invalid_output")
        )
        == "lease_lost"
    )
    await db_session.refresh(job)
    await db_session.refresh(r)
    assert job.status == "uncertain" and r.state == "known" and r.input_tokens == 100
    assert await db_session.scalar(select(Item.id).where(Item.job_id == job.id)) is None


async def test_reserved_slot_keeps_utc_day_across_midnight_and_usage_conflicts_fail_closed(
    db_session, monkeypatch
):
    from app.finance.categorization_context import CategorizationError
    from app.finance.suggestion_client import ProviderUsage
    from app.finance.suggestion_jobs import admit_suggestion_dispatch
    from app.finance.suggestion_usage import record_suggestion_usage, reserve_suggestion_call

    _, _, _, _, _, txn = await suggestion_ready(db_session, monkeypatch)
    lease, packet = await prepared(db_session, await job_for(db_session, txn))
    row = await reserve_suggestion_call(db_session, lease, packet)
    await db_session.commit()
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    row.usage_date = yesterday
    await db_session.commit()
    replay = await reserve_suggestion_call(db_session, lease, packet)
    assert replay.usage_date == yesterday
    ticket = await admit_suggestion_dispatch(db_session, lease, row.reservation_version)
    await db_session.commit()
    await record_suggestion_usage(db_session, ticket, ProviderUsage(100, 20, "e" * 64))
    await db_session.commit()
    with pytest.raises(CategorizationError, match="już zapisane"):
        await record_suggestion_usage(db_session, ticket, ProviderUsage(999, 20, "e" * 64))
    await db_session.rollback()


async def test_expired_lease_during_grant_validation_cannot_admit(db_session, monkeypatch):
    from app.finance import suggestion_jobs
    from app.finance.suggestion_usage import reserve_suggestion_call

    _, _, _, _, _, txn = await suggestion_ready(db_session, monkeypatch)
    job = await job_for(db_session, txn)
    lease, packet = await prepared(db_session, job)
    row = await reserve_suggestion_call(db_session, lease, packet)
    await db_session.commit()
    original = suggestion_jobs.validated_context

    async def expire(db, claimed):
        result = await original(db, claimed)
        claimed.lease_deadline = datetime.now(UTC) - timedelta(seconds=1)
        return result

    monkeypatch.setattr(suggestion_jobs, "validated_context", expire)
    assert (
        await suggestion_jobs.admit_suggestion_dispatch(db_session, lease, row.reservation_version)
        is None
    )
    await db_session.refresh(row)
    assert row.state == "reserved"
