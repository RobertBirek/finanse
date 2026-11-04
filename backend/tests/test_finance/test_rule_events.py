"""Future-only enrollment and lease-fenced rule mutation through the real ledger."""

from datetime import date

import pytest
from sqlalchemy import func, select

from app.finance import service
from app.finance.categorization_context import columns
from app.finance.models import FinanceCommandReceipt, Posting, TransactionCategorizationState
from app.finance.schemas import PostingCreate, TransactionCreate
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_rule_policy import ROOT, approve, configured, draft, mutate

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def new_expense(db, owner, account, marker, description="Czynsz mieszkanie", **changes):
    return await service.create_transaction(
        db,
        owner,
        TransactionCreate(
            type="expense",
            description=description,
            transaction_date=date(2026, 2, 2),
            postings=[
                PostingCreate(
                    account_id=account.id,
                    source_amount=10000,
                    base_amount_pln=10000,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=marker.id,
                    source_amount=10000,
                    base_amount_pln=10000,
                    direction="credit",
                ),
            ],
            **changes,
        ),
    )


async def ready(db):
    owner, old, account, marker, target = await configured(db)
    async with client_for(db, owner) as client:
        rule = await approve(client, await draft(client, target.id))
        response = await client.get(ROOT + "/events?status=active")
        assert response.status_code == 200, response.text
    txn = await new_expense(db, owner, account, marker)
    await db.commit()
    return owner, old, account, marker, target, rule, txn


async def event_for(db, txn):
    from app.finance.rule_events import TransactionRuleEvent

    return await db.scalar(
        select(TransactionRuleEvent)
        .where(TransactionRuleEvent.transaction_id == txn.id)
        .execution_options(populate_existing=True)
    )


async def process(db, event):
    from app.finance.rule_events import apply_rule_event, claim_rule_event

    lease = await claim_rule_event(db, event.id)
    await db.commit()
    assert lease is not None
    result = await apply_rule_event(db, lease)
    await db.commit()
    return result


async def test_rule_job_writes_origin_without_manualstate_or_payment_changes(db_session):
    from app.finance.rule_models import TransactionCategorizationOrigin as Origin

    _owner, old, _account, _marker, target, rule, txn = await ready(db_session)
    event = await event_for(db_session, txn)
    assert event is not None and event.status == "ready"
    original = columns(next(p for p in txn.postings if p.account_id))
    date_before = txn.date
    assert await event_for(db_session, old) is None
    assert (await process(db_session, event)) == "applied"
    await db_session.refresh(txn, ["postings"])
    assert columns(next(p for p in txn.postings if p.account_id)) == original
    assert next(p for p in txn.postings if p.category_id).category_id == target.id
    assert txn.date == date_before and txn.source == "manual"
    assert (
        sum(
            p.base_amount_pln if p.direction == "debit" else -p.base_amount_pln
            for p in txn.postings
        )
        == 0
    )
    assert (
        await db_session.scalar(select(func.count()).select_from(TransactionCategorizationState))
        == 0
    )
    origin = await db_session.scalar(select(Origin).where(Origin.transaction_id == txn.id))
    assert origin.origin == "approved_rule" and str(origin.rule_id) == rule["id"]
    assert str(origin.approval_receipt_id) == rule["approval_receipt_id"]
    async with client_for(db_session, _owner) as client:
        listed = await client.get("/api/finance/transactions/search")
        assert listed.status_code == 200, listed.text
        item = next(t for t in listed.json()["items"] if t["id"] == str(txn.id))
        assert (
            item.get("assignment_origin", {}).get("display_description")
            == rule["display_description"]
        )
    from app.finance.rule_events import claim_rule_event

    assert await claim_rule_event(db_session, event.id) is None


async def test_only_creation_enrolls_observed_approval_without_history_discovery(db_session):
    owner, old, account, marker, target = await configured(db_session)
    txn = await new_expense(db_session, owner, account, marker)
    await db_session.commit()
    event = await event_for(db_session, txn)
    assert event.status == "skipped" and event.reason_code == "no_match"
    async with client_for(db_session, owner) as client:
        await approve(client, await draft(client, target.id))
        active = await client.get(ROOT + "/events?status=active")
        assert active.status_code == 200, active.text
        assert active.json()["events"] == []
    from app.finance.rule_events import claim_rule_event

    assert await claim_rule_event(db_session, event.id) is None
    assert await event_for(db_session, old) is None


@pytest.mark.parametrize("description", ["Czynsz mieszkanie dodatkowy", "czynsz", "mieszkanie"])
async def test_exact_match_never_substring(db_session, description):
    owner, _, account, marker, _, _, _ = await ready(db_session)
    txn = await new_expense(db_session, owner, account, marker, description)
    event = await event_for(db_session, txn)
    assert event.status == "skipped" and event.reason_code == "no_match"


@pytest.mark.parametrize(
    "change",
    ["settings", "pause", "marker_archive", "target_rename", "manual_confirm", "input", "account"],
)
async def test_delayed_worker_revalidates_policy_marker_ledger_and_manual_protection(
    db_session, change
):
    owner, _, account, marker, target, rule, txn = await ready(db_session)
    event = await event_for(db_session, txn)
    if change == "settings":
        async with client_for(db_session, owner) as client:
            s = (await client.get(ROOT + "/settings")).json()
            assert (
                await mutate(
                    client,
                    "patch",
                    "/settings",
                    {
                        "expected_version": s["version"],
                        "rules_enabled": False,
                        "uncategorized_category_id": str(marker.id),
                        "confirm_future_only": True,
                    },
                )
            ).status_code == 200
    if change == "pause":
        async with client_for(db_session, owner) as client:
            assert (
                await mutate(
                    client,
                    "post",
                    f"/rules/{rule['id']}/pause",
                    {"expected_version": rule["version"]},
                )
            ).status_code == 200
    if change == "marker_archive":
        marker.is_active = False
    if change == "target_rename":
        target.name = "Inny sens"
    if change == "manual_confirm":
        from tests.test_finance.test_categorization import apply, preview

        async with client_for(db_session, owner) as client:
            p = await preview(client, txn, [{"category_id": str(marker.id), "amount_minor": 10000}])
            assert (await apply(client, txn, p)).status_code == 200
    if change == "input":
        txn.description = "Nowy opis"
    if change == "account":
        account.is_budget_account = False
    await db_session.commit()
    original = columns(next(p for p in txn.postings if p.account_id))
    assert await process(db_session, event) == "skipped"
    await db_session.refresh(txn, ["postings"])
    assert next(p for p in txn.postings if p.category_id).category_id == marker.id
    assert columns(next(p for p in txn.postings if p.account_id)) == original


async def test_broker_outage_does_not_spend_attempt_or_lose_ready_event(db_session, monkeypatch):
    from redis.exceptions import ConnectionError as RedisConnectionError
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.finance import rule_worker

    _owner, _, _, _, _, _, txn = await ready(db_session)
    event = await event_for(db_session, txn)
    monkeypatch.setattr(
        rule_worker,
        "async_session_factory",
        async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False),
    )

    class Offline:
        async def enqueue_job(self, *args):
            raise RedisConnectionError("offline")

    await rule_worker.dispatch_rule_events({"redis": Offline()})
    await db_session.refresh(event)
    assert event.status == "ready" and event.attempts == 0
    assert await rule_worker.process_rule_event({}, str(event.id)) == "applied"
    assert await rule_worker.process_rule_event({}, str(event.id)) == "not_claimed"
    await db_session.refresh(event)
    assert event.status == "applied" and event.attempts == 1


async def test_audit_failure_rolls_back_writer_then_failure_cas_is_separate(
    db_session, monkeypatch
):
    from app.finance import rule_events

    _owner, _, _, marker, _target, _, txn = await ready(db_session)
    event = await event_for(db_session, txn)
    event_id, txn_id, marker_id = event.id, txn.id, marker.id
    lease = await rule_events.claim_rule_event(db_session, event_id)
    await db_session.commit()

    async def fail(*args, **kwargs):
        raise RuntimeError("test failure")

    monkeypatch.setattr(rule_events, "log_event", fail)
    with pytest.raises(RuntimeError):
        await rule_events.apply_rule_event(db_session, lease)
    await db_session.rollback()
    await rule_events.record_rule_event_failure(db_session, lease, "write_failed")
    await db_session.commit()
    event = await db_session.get(rule_events.TransactionRuleEvent, event_id)
    await db_session.refresh(event)
    assert event.status == "ready" and event.attempts == 1
    assert (
        await db_session.scalar(
            select(Posting.category_id).where(
                Posting.transaction_id == txn_id, Posting.category_id.is_not(None)
            )
        )
        == marker_id
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(FinanceCommandReceipt)
            .where(FinanceCommandReceipt.action == "apply_approved_category_rule")
        )
        == 0
    )


async def test_manual_correction_audits_prior_immutable_rule_origin(db_session):
    from app.audit.models import AuditEvent
    from tests.test_finance.test_categorization import apply, preview

    owner, _, _, marker, _, rule, txn = await ready(db_session)
    await process(db_session, await event_for(db_session, txn))
    async with client_for(db_session, owner) as client:
        p = await preview(client, txn, [{"category_id": str(marker.id), "amount_minor": 10000}])
        result = await apply(client, txn, p)
        assert result.status_code == 200, result.text
        assert result.json()["assignment_origin"]["origin"] == "manual"
    audit = await db_session.scalar(
        select(AuditEvent).where(AuditEvent.action == "apply_expense_categorization")
    )
    assert audit.old_state.get("assignment_origin", {}).get("rule_id") == rule["id"]


async def test_expired_lease_recovery_caps_attempts_and_stolen_token_cannot_write(
    db_session, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    from app.config import settings
    from app.finance import rule_events

    _owner, _, _, marker, _, _, txn = await ready(db_session)
    event = await event_for(db_session, txn)
    monkeypatch.setattr(settings, "FINANCE_RULE_MAX_ATTEMPTS", 2)
    first = await rule_events.claim_rule_event(db_session, event.id)
    await db_session.commit()
    event.lease_deadline = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    second = await rule_events.claim_rule_event(db_session, event.id)
    await db_session.commit()
    assert first.token != second.token
    assert await rule_events.apply_rule_event(db_session, first) == "lease_lost"
    await rule_events.record_rule_event_failure(db_session, first, "write_failed")
    await db_session.commit()
    await db_session.refresh(event)
    assert event.lease_token == second.token and event.status == "processing"
    event.lease_deadline = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    assert await rule_events.claim_rule_event(db_session, event.id) is None
    await db_session.commit()
    await db_session.refresh(event)
    assert event.status == "failed" and event.attempts == 2
    assert next(p for p in txn.postings if p.category_id).category_id == marker.id
    assert await rule_events.claim_rule_event(db_session, event.id) is None


@pytest.mark.parametrize(
    "source,pending",
    [
        ("actual", False),
        ("scheduled_confirmation", False),
        ("document_payment", False),
        ("manual", True),
    ],
)
async def test_protected_creation_paths_never_enroll(db_session, source, pending):
    owner, _, account, marker, _, _, _ = await ready(db_session)
    txn = await new_expense(db_session, owner, account, marker, source=source, is_pending=pending)
    assert await event_for(db_session, txn) is None


@pytest.mark.parametrize("description", [" ", "x" * 501])
async def test_ineligible_description_never_prevents_recording_payment(db_session, description):
    owner, _, account, marker, _, _, _ = await ready(db_session)
    txn = await new_expense(db_session, owner, account, marker, description)
    assert (await event_for(db_session, txn)).status == "skipped"


async def test_event_and_payment_rollback_together_and_duplicate_enrollment_is_noop(db_session):
    from app.finance.models import FinancialTransaction
    from app.finance.rule_events import TransactionRuleEvent, record_new_expense_event

    owner, _, account, marker, _, _, txn = await ready(db_session)
    event = await event_for(db_session, txn)
    assert await record_new_expense_event(db_session, owner, txn) == event.id
    assert await db_session.scalar(select(func.count()).select_from(TransactionRuleEvent)) == 1
    pending = await new_expense(db_session, owner, account, marker)
    pending_id = pending.id
    await db_session.rollback()
    assert await db_session.get(FinancialTransaction, pending_id) is None
    assert await db_session.scalar(select(func.count()).select_from(TransactionRuleEvent)) == 1


@pytest.mark.parametrize(
    "protection", ["actual_mapping", "fx", "pending", "refund", "legacy_manual_state"]
)
async def test_delayed_rule_never_rewrites_protected_ledger(db_session, protection):
    from app.finance.models import ActualImportMapping

    _owner, _, _, marker, _, _, txn = await ready(db_session)
    event = await event_for(db_session, txn)
    if protection == "actual_mapping":
        db_session.add(
            ActualImportMapping(
                user_id=txn.user_id, entity_type="transaction", entity_id=txn.id, actual_id="pinned"
            )
        )
    if protection == "fx":
        txn.postings[0].fx_rate = 4
    if protection == "pending":
        txn.is_pending = True
    if protection == "refund":
        for p in txn.postings:
            p.direction = "credit" if p.account_id else "debit"
    if protection == "legacy_manual_state":
        db_session.add(
            TransactionCategorizationState(
                transaction_id=txn.id,
                user_id=txn.user_id,
                version=1,
                source="manual",
                before_snapshot_sha256="a" * 64,
                after_snapshot_sha256="b" * 64,
            )
        )
    await db_session.flush()
    await db_session.refresh(txn, ["postings", "updated_at"])
    await db_session.commit()
    original = [columns(p) for p in txn.postings]
    assert await process(db_session, event) == "skipped"
    await db_session.refresh(txn, ["postings"])
    assert [columns(p) for p in txn.postings] == original
    assert next(p for p in txn.postings if p.category_id).category_id == marker.id
