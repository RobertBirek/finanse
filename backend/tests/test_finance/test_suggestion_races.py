"""Admitted calls are at-most-once; a late response never revives publication rights."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.finance.suggestion_models import (
    CategorizationLlmUsageReservation as Reservation,
)
from app.finance.suggestion_models import (
    CategorizationProposalItem as Item,
)
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_rule_policy import mutate
from tests.test_finance.test_suggestion_jobs import job_for, suggestion_ready

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def change_source(db, owner, txn, marker, kind, monkeypatch):
    from app.config import settings

    if kind == "disable":
        async with client_for(db, owner) as client:
            r = await mutate(
                client, "patch", "/suggestions/settings", {"expected_version": 1, "enabled": False}
            )
            assert r.status_code == 200, r.text
    elif kind == "config":
        monkeypatch.setattr(settings, "FINANCE_SUGGESTIONS_MODEL", "different-test-only")
    elif kind == "marker":
        marker.is_active = False
    elif kind == "source":
        txn.description = "Changed source"
    elif kind == "manual":
        from tests.test_finance.test_categorization import apply, preview

        async with client_for(db, owner) as client:
            p = await preview(client, txn, [{"category_id": str(marker.id), "amount_minor": 10000}])
            assert (await apply(client, txn, p)).status_code == 200
    else:
        from app.identity.models import User

        user = await db.get(User, owner)
        user.is_active = False
    await db.commit()


@pytest.mark.parametrize("kind", ["disable", "config", "marker", "source", "manual", "identity"])
async def test_revoke_before_admission_means_zero_provider_calls(db_session, monkeypatch, kind):
    from app.finance import suggestion_worker

    owner, _, _, marker, _, txn = await suggestion_ready(db_session, monkeypatch)
    job = await job_for(db_session, txn)
    await change_source(db_session, owner, txn, marker, kind, monkeypatch)

    async def unexpected(*args):
        pytest.fail("Revoked generation cannot send")

    monkeypatch.setattr(suggestion_worker, "call_suggestion_provider", unexpected)
    monkeypatch.setattr(
        suggestion_worker,
        "async_session_factory",
        async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False),
    )
    assert await suggestion_worker.process_suggestion_job({}, str(job.id)) == "cancelled"
    assert (
        await db_session.scalar(select(Reservation.id).where(Reservation.job_id == job.id)) is None
    )


@pytest.mark.parametrize("kind", ["disable", "config", "marker", "source", "manual", "identity"])
async def test_after_dispatch_revoke_does_not_hold_locks_or_publish_but_keeps_known_usage(
    db_session, monkeypatch, kind
):
    from app.finance import suggestion_worker
    from app.finance.suggestion_client import ProviderOutcome, ProviderUsage
    from app.finance.suggestion_schemas import SuggestionPayload

    owner, _, _, marker, target, txn = await suggestion_ready(db_session, monkeypatch)
    job = await job_for(db_session, txn)
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def provider(packet, config):
        calls.append(1)
        started.set()
        await release.wait()
        key = next(k for k, v in packet.private_key_map.items() if v == target.id)
        return ProviderOutcome(
            SuggestionPayload(
                decision="existing_category",
                category_key=key,
                confidence="high",
                explanation="Reason",
                new_category=None,
            ),
            ProviderUsage(100, 25, "c" * 64),
        )

    monkeypatch.setattr(suggestion_worker, "call_suggestion_provider", provider)
    monkeypatch.setattr(
        suggestion_worker,
        "async_session_factory",
        async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False),
    )
    task = asyncio.create_task(suggestion_worker.process_suggestion_job({}, str(job.id)))
    try:
        await asyncio.wait_for(started.wait(), 10)
        await asyncio.wait_for(change_source(db_session, owner, txn, marker, kind, monkeypatch), 10)
    finally:
        release.set()
    assert await asyncio.wait_for(task, 10) == "cancelled"
    row = await db_session.scalar(select(Reservation).where(Reservation.job_id == job.id))
    assert row.state == "known" and row.input_tokens == 100
    assert (
        len(calls) == 1
        and await db_session.scalar(select(Item.id).where(Item.job_id == job.id)) is None
    )


@pytest.mark.parametrize("after_commit", [False, True])
async def test_admission_commit_failure_or_ambiguous_commit_never_sends(
    db_session, monkeypatch, after_commit
):
    from app.finance import suggestion_worker

    _owner, _, _, _, _, txn = await suggestion_ready(db_session, monkeypatch)
    job = await job_for(db_session, txn)
    original = suggestion_worker.admit_suggestion_dispatch

    async def admission(db, *args):
        result = await original(db, *args)
        if result:
            db.info["inject_commit_failure"] = True
        return result

    class FailingSession(AsyncSession):
        async def commit(self):
            if self.info.pop("inject_commit_failure", False):
                if after_commit:
                    await super().commit()
                raise RuntimeError("Test uncertain commit")
            await super().commit()

    async def unexpected(*args):
        pytest.fail("No proof of admission commit, no send")

    monkeypatch.setattr(suggestion_worker, "admit_suggestion_dispatch", admission)
    monkeypatch.setattr(
        suggestion_worker,
        "async_session_factory",
        async_sessionmaker(db_session.bind, class_=FailingSession, expire_on_commit=False),
    )
    monkeypatch.setattr(suggestion_worker, "call_suggestion_provider", unexpected)
    assert await suggestion_worker.process_suggestion_job({}, str(job.id)) == "not_admitted"
    await db_session.refresh(job)
    assert job.status == ("dispatching" if after_commit else "reserved")


async def test_creation_does_not_wait_for_policy_or_rule_fk_and_observes_once(
    db_session, monkeypatch
):
    from app.finance.suggestion_models import (
        CategorizationLlmPolicy as Policy,
    )
    from app.finance.suggestion_models import (
        CategorizationSuggestionSettings as Consent,
    )
    from tests.test_finance.test_rule_events import new_expense

    owner, _, account, marker, _, _ = await suggestion_ready(db_session, monkeypatch)
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if "anon_1" in statement and "categorization_suggestion_settings" in statement:
            statements.append(statement)

    async with sessions() as held:
        await held.scalar(select(Consent).where(Consent.user_id == owner).with_for_update())
        await held.scalar(select(Policy).with_for_update())
        event.listen(db_session.bind.sync_engine, "before_cursor_execute", record)
        try:
            async with sessions() as source:
                txn = await asyncio.wait_for(
                    new_expense(source, owner, account, marker, "Other"), 10
                )
                await source.commit()
                assert await job_for(source, txn)
        finally:
            event.remove(db_session.bind.sync_engine, "before_cursor_execute", record)
        assert len(statements) == 1


@pytest.mark.parametrize(
    "changed", [None, "date", "account", "postings", "mapping", "manualstate", "origin"]
)
async def test_legacy_v2_rule_opportunity_preserves_all_guards(db_session, changed):
    # Hand-build the complete old v2 payload, independent of the new helper.
    from app.finance.categorization_context import columns, digest, load_context
    from app.finance.models import ActualImportMapping, TransactionCategorizationState
    from app.finance.rule_models import TransactionCategorizationOrigin
    from tests.test_finance.test_rule_events import event_for, process, ready

    owner, _, account, _marker, _, _, txn = await ready(db_session)
    eventrow = await event_for(db_session, txn)
    ctx = await load_context(db_session, owner, txn.id)
    old = digest(
        {
            "schema": "expense-categorization-v2",
            "origin": None,
            "transaction": columns(ctx.txn),
            "postings": [columns(p) for p in sorted(ctx.txn.postings, key=lambda p: str(p.id))],
            "account": columns(ctx.account),
            "dates": columns(ctx.dates) if ctx.dates else None,
            "state": None,
            "mappings": [],
            "loans": [],
            "allocations": [],
        }
    )
    eventrow.source_context_sha256 = old
    if changed == "date":
        txn.date = txn.date + timedelta(days=1)
    if changed == "account":
        account.name = "Changed account"
    if changed == "postings":
        txn.postings[0].is_budget_impact = False
    if changed == "mapping":
        db_session.add(
            ActualImportMapping(
                user_id=owner,
                actual_id="test-legacy",
                entity_type="transaction",
                entity_id=txn.id,
            )
        )
    if changed == "manualstate":
        db_session.add(
            TransactionCategorizationState(
                transaction_id=txn.id,
                user_id=owner,
                version=1,
                source="manual",
                before_snapshot_sha256="a" * 64,
                after_snapshot_sha256="b" * 64,
            )
        )
    if changed == "origin":
        db_session.add(
            TransactionCategorizationOrigin(
                transaction_id=txn.id,
                user_id=owner,
                origin="manual",
                version=1,
                assignment_sha256="a" * 64,
            )
        )
    await db_session.commit()
    assert await process(db_session, eventrow) == ("applied" if changed is None else "skipped")


@pytest.mark.parametrize("first_operation", ["dispatch", "server_off"])
async def test_global_policy_rotation_and_dispatch_have_no_lock_inversion(
    db_session, monkeypatch, first_operation
):
    from app.config import settings
    from app.finance.suggestion_config import get_suggestion_config
    from app.finance.suggestion_jobs import admit_suggestion_dispatch
    from app.finance.suggestion_policy import set_suggestion_policy
    from app.finance.suggestion_usage import reserve_suggestion_call
    from tests.test_finance.test_categorization_races import wait_for_database_lock
    from tests.test_finance.test_suggestion_usage import prepared

    owner, _, _, _, _, txn = await suggestion_ready(db_session, monkeypatch)
    lease, packet = await prepared(db_session, await job_for(db_session, txn))
    row = await reserve_suggestion_call(db_session, lease, packet)
    await db_session.commit()
    version = row.reservation_version
    config = get_suggestion_config(settings)
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    admitted, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids = []
    tickets = []

    async def operation(db, kind):
        if kind == "dispatch":
            tickets.append(await admit_suggestion_dispatch(db, lease, version))
        else:
            await set_suggestion_policy(
                db, enabled=False, expected_epoch=1, performed_by=owner, config=config
            )

    async def first():
        async with sessions() as db:
            await operation(db, first_operation)
            admitted.set()
            await release.wait()
            await db.commit()

    async def second():
        await admitted.wait()
        async with sessions() as db:
            pids.append(await db.scalar(text("SELECT pg_backend_pid()")))
            waiting.set()
            await operation(db, "server_off" if first_operation == "dispatch" else "dispatch")
            await db.commit()

    a, b = asyncio.create_task(first()), asyncio.create_task(second())
    try:
        await asyncio.wait_for(waiting.wait(), 10)
        await wait_for_database_lock(db_session, pids[0])
        assert not b.done()
    finally:
        release.set()
        results = await asyncio.wait_for(asyncio.gather(a, b, return_exceptions=True), 15)
    assert not any(isinstance(r, BaseException) for r in results), results
    assert bool(tickets[0]) == (first_operation == "dispatch")
