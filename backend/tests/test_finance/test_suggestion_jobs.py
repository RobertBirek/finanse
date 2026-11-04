"""Creation-only intents and conservative paid-call dispatch are durable in PostgreSQL."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.finance.categorization_context import columns
from app.finance.models import FinancialTransaction, TransactionCategorizationState
from app.finance.suggestion_models import (
    CategorizationLlmUsageReservation as Reservation,
)
from app.finance.suggestion_models import (
    CategorizationProposalItem as Item,
)
from app.finance.suggestion_models import (
    CategorizationSuggestionJob as Job,
)
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_rule_events import event_for, new_expense, process
from tests.test_finance.test_rule_policy import ROOT, approve, configured, draft, mutate
from tests.test_finance.test_suggestion_policy import enable_server, optin

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def suggestion_ready(db, monkeypatch, *, rules_enabled=False):
    owner, old, account, marker, target = await configured(db)
    if not rules_enabled:
        async with client_for(db, owner) as client:
            s = (await client.get(ROOT + "/settings")).json()
            r = await mutate(
                client,
                "patch",
                "/settings",
                {
                    "expected_version": s["version"],
                    "uncategorized_category_id": str(marker.id),
                    "rules_enabled": False,
                    "confirm_future_only": True,
                },
            )
            assert r.status_code == 200, r.text
    await enable_server(db, owner, monkeypatch)
    async with client_for(db, owner) as client:
        r = await optin(client)
        assert r.status_code == 200, r.text
    txn = await new_expense(db, owner, account, marker)
    await db.commit()
    return owner, old, account, marker, target, txn


async def job_for(db, txn):
    return await db.scalar(
        select(Job).where(Job.transaction_id == txn.id).execution_options(populate_existing=True)
    )


@pytest.mark.parametrize("rules_enabled", [False, True])
async def test_creation_only_rules_off_ai_on_and_old_sources_never_discovered(
    db_session, monkeypatch, rules_enabled
):
    owner, old, _, _, _, txn = await suggestion_ready(
        db_session, monkeypatch, rules_enabled=rules_enabled
    )
    job = await job_for(db_session, txn)
    assert job is not None and job.status == "ready" and job.attempts == 0
    assert await job_for(db_session, old) is None
    assert txn.date.year == 2026 and txn.date.month == 2  # old booking date is still a new creation
    async with client_for(db_session, owner) as client:
        activity = await client.get(ROOT + "/suggestions/activity")
        assert activity.status_code == 200, activity.text
        assert [j["id"] for j in activity.json()["active_jobs"]] == [str(job.id)]
        assert "packet_json" not in activity.text and "private_key_map" not in activity.text


async def test_rule_candidate_wins_and_ai_never_falls_back_from_failed_rule(
    db_session, monkeypatch
):
    owner, _, account, marker, target, first = await suggestion_ready(
        db_session, monkeypatch, rules_enabled=True
    )
    async with client_for(db_session, owner) as client:
        await approve(client, await draft(client, target.id))
    txn = await new_expense(db_session, owner, account, marker)
    await db_session.commit()
    assert await job_for(db_session, txn) is None
    target.name = "Different meaning"
    await db_session.commit()
    event = await event_for(db_session, txn)
    assert await process(db_session, event) == "skipped"
    assert await job_for(db_session, txn) is None
    assert (await job_for(db_session, first)).status == "ready"


async def test_creation_rollback_and_duplicate_hook_keep_one_opportunity(db_session, monkeypatch):
    from app.finance.categorization_enrollment import observe_creation_policy
    from app.finance.suggestion_jobs import record_new_suggestion_intent

    owner, _, account, marker, _, txn = await suggestion_ready(db_session, monkeypatch)
    job = await job_for(db_session, txn)
    observed = await observe_creation_policy(db_session, owner, txn.description)
    assert await record_new_suggestion_intent(db_session, owner, txn, observed) == job.id
    assert await db_session.scalar(select(func.count()).select_from(Job)) == 1
    other = await new_expense(db_session, owner, account, marker, "Other")
    other_id = other.id
    await db_session.rollback()
    assert (
        await db_session.scalar(
            select(FinancialTransaction.id).where(FinancialTransaction.id == other_id)
        )
        is None
    )
    assert await db_session.scalar(select(Job.id).where(Job.transaction_id == other_id)) is None


@pytest.mark.parametrize(
    "outcome_kind", ["existing_category", "new_category", "no_suggestion", "invalid", "uncertain"]
)
async def test_worker_publishes_only_valid_proposals_without_ledger_writes_and_never_sends_twice(
    db_session, monkeypatch, outcome_kind
):
    from app.finance import suggestion_worker
    from app.finance.suggestion_client import ProviderOutcome, ProviderUsage
    from app.finance.suggestion_schemas import SuggestionPayload

    _owner, _, _, _marker, target, txn = await suggestion_ready(db_session, monkeypatch)
    job = await job_for(db_session, txn)
    before = [columns(p) for p in txn.postings]
    txn_before = columns(txn)
    calls = []

    async def fake(packet, config):
        calls.append(packet.request_sha256)
        if outcome_kind in {"invalid", "uncertain"}:
            return ProviderOutcome(
                None,
                ProviderUsage()
                if outcome_kind == "uncertain"
                else ProviderUsage(123, 45, "a" * 64),
                "provider_uncertain" if outcome_kind == "uncertain" else "invalid_output",
                outcome_kind == "uncertain",
            )
        key = next(k for k, v in packet.private_key_map.items() if v == target.id)
        payload = SuggestionPayload(
            decision=outcome_kind,
            category_key=key if outcome_kind == "existing_category" else None,
            confidence="high",
            explanation="Reason",
            new_category={"name": "Suggested", "parent_key": key, "explanation": "Reason"}
            if outcome_kind == "new_category"
            else None,
        )
        return ProviderOutcome(payload, ProviderUsage(123, 45, "a" * 64))

    monkeypatch.setattr(suggestion_worker, "call_suggestion_provider", fake)
    monkeypatch.setattr(
        suggestion_worker,
        "async_session_factory",
        async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False),
    )
    result = await suggestion_worker.process_suggestion_job({}, str(job.id))
    assert result in {"completed", "failed", "uncertain"}
    assert await suggestion_worker.process_suggestion_job({}, str(job.id)) == "not_claimed"
    assert len(calls) == 1
    await db_session.refresh(txn, ["postings"])
    assert [columns(p) for p in txn.postings] == before
    assert columns(txn) == txn_before
    item = await db_session.scalar(select(Item).where(Item.job_id == job.id))
    assert bool(item) == (outcome_kind in {"existing_category", "new_category"})
    if item:
        assert item.status == "pending" and item.confidence == "high"
        assert item.target_category_id == (
            target.id if outcome_kind == "existing_category" else None
        )
    reservation = await db_session.scalar(select(Reservation).where(Reservation.job_id == job.id))
    assert reservation.state == ("unknown" if outcome_kind == "uncertain" else "known")
    assert (
        await db_session.scalar(select(func.count()).select_from(TransactionCategorizationState))
        == 0
    )


async def test_disabled_generation_never_enrolls_backlog_or_calls_provider(db_session, monkeypatch):
    from app.finance import suggestion_worker

    owner, old, account, marker, _, txn = await suggestion_ready(db_session, monkeypatch)
    job = await job_for(db_session, txn)
    async with client_for(db_session, owner) as client:
        r = await mutate(
            client, "patch", "/suggestions/settings", {"expected_version": 1, "enabled": False}
        )
        assert r.status_code == 200
    later = await new_expense(db_session, owner, account, marker, "While OFF")
    await db_session.commit()

    async def unexpected(*args):
        pytest.fail("Disabled generation must not dispatch a provider call")

    monkeypatch.setattr(suggestion_worker, "call_suggestion_provider", unexpected)
    monkeypatch.setattr(
        suggestion_worker,
        "async_session_factory",
        async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False),
    )
    assert await suggestion_worker.process_suggestion_job({}, str(job.id)) == "cancelled"
    assert await job_for(db_session, later) is None
    async with client_for(db_session, owner) as client:
        assert (await optin(client, 2)).status_code == 200
    await suggestion_worker.dispatch_suggestion_jobs(
        {"redis": type("Broker", (), {"enqueue_job": unexpected})()}
    )
    assert await job_for(db_session, old) is None and await job_for(db_session, later) is None
