"""Only actual human approval can turn an AI suggestion into a ledger assignment."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.finance.categorization_context import columns
from app.finance.models import (
    FinanceCommandReceipt,
    FinancialTransaction,
    Posting,
    TransactionCategorizationState,
)
from app.finance.suggestion_models import CategorizationProposalItem as Item
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_rule_policy import ROOT, mutate
from tests.test_finance.test_suggestion_jobs import job_for, suggestion_ready

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def proposed(db, monkeypatch, *, decision="existing_category"):
    from app.finance import suggestion_worker
    from app.finance.suggestion_client import ProviderOutcome, ProviderUsage
    from app.finance.suggestion_schemas import SuggestionPayload

    owner, _old, account, marker, target, txn = await suggestion_ready(db, monkeypatch)

    async def provider(packet, config):
        key = next(k for k, v in packet.private_key_map.items() if v == target.id)
        return ProviderOutcome(
            SuggestionPayload(
                decision=decision,
                category_key=key if decision == "existing_category" else None,
                confidence="high",
                explanation="Opis odpowiada kategorii",
                new_category={
                    "name": "Nowa kategoria",
                    "parent_key": key,
                    "explanation": "Do osobnego utworzenia",
                }
                if decision == "new_category"
                else None,
            ),
            ProviderUsage(100, 20, "f" * 64),
        )

    monkeypatch.setattr(suggestion_worker, "call_suggestion_provider", provider)
    monkeypatch.setattr(
        suggestion_worker,
        "async_session_factory",
        async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False),
    )
    job = await job_for(db, txn)
    assert await suggestion_worker.process_suggestion_job({}, str(job.id)) == "completed"
    item = await db.scalar(select(Item).where(Item.job_id == job.id))
    assert item
    return owner, account, marker, target, txn, item


async def preview(client, item):
    r = await client.post(
        f"{ROOT}/proposals/{item.id}/preview", json={"expected_version": item.version}
    )
    assert r.status_code == 200, r.text
    return r.json()


async def apply(client, item, p, key=None, **extra):
    return await mutate(
        client,
        "post",
        f"/proposals/{item.id}/apply",
        {
            "expected_version": p["expected_version"],
            "preview_snapshot": p["preview_snapshot"],
            "confirmed": True,
            **extra,
        },
        key,
    )


async def test_queue_preview_are_owned_nonmutating_and_review_survives_ai_off(
    db_session, monkeypatch
):
    from tests.test_finance.test_bill_payments import create_owner

    owner, _, _, _, txn, item = await proposed(db_session, monkeypatch)
    count = await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt))
    before = columns(txn)
    async with client_for(db_session, owner) as client:
        page = await client.get(ROOT + "/proposals")
        assert page.status_code == 200, page.text
        assert len(page.json()["items"]) == 1
        row = page.json()["items"][0]
        assert row["eligible"] is True and row["amount_minor"] == 10000
        assert "private_key_map" not in page.text
        p = await preview(client, item)
        assert p["amount_minor"] == 10000 and p["after_parts"][0]["amount_minor"] == 10000
        assert (
            await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt))
            == count
        )
        await mutate(
            client, "patch", "/suggestions/settings", {"expected_version": 1, "enabled": False}
        )
        assert (await preview(client, item))["preview_snapshot"] == p["preview_snapshot"]
    assert columns(txn) == before
    other = await create_owner(db_session)
    await db_session.commit()
    async with client_for(db_session, other) as client:
        assert (await client.get(ROOT + "/proposals")).json()["items"] == []
        assert (await client.get(f"{ROOT}/proposals/{item.id}")).status_code == 404
        assert (
            await client.post(f"{ROOT}/proposals/{item.id}/preview", json={"expected_version": 1})
        ).status_code == 404


async def test_apply_exact_grosze_preserves_payment_and_records_human_protected_ai_origin(
    db_session, monkeypatch
):
    from app.finance.rule_models import TransactionCategorizationOrigin as Origin

    owner, _, _, target, txn, item = await proposed(db_session, monkeypatch)
    txn_id = txn.id
    target_id, item_id = target.id, item.id
    before_account = columns(next(p for p in txn.postings if p.account_id))
    before = columns(txn)
    async with client_for(db_session, owner) as client:
        p = await preview(client, item)
        key = uuid.uuid4().hex
        result = await apply(client, item, p, key)
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "approved"
        assert result.json()["context"]["assignment_origin"]["origin"] == "approved_llm"
        assert (await apply(client, item, p, key)).json() == result.json()
        assert (await apply(client, item, p, key, expected_version=2)).status_code == 409
    await db_session.refresh(txn)
    await db_session.refresh(txn, ["postings"])
    assert columns(next(p for p in txn.postings if p.account_id)) == before_account
    assert (
        txn.id == txn_id
        and txn.date.isoformat() == before["date"]
        and txn.source == before["source"]
    )
    assert next(p.category_id for p in txn.postings if p.category_id) == target_id
    assert sum(p.base_amount_pln * (1 if p.direction == "debit" else -1) for p in txn.postings) == 0
    origin = await db_session.scalar(select(Origin).where(Origin.transaction_id == txn.id))
    state = await db_session.scalar(
        select(TransactionCategorizationState).where(
            TransactionCategorizationState.transaction_id == txn.id
        )
    )
    assert (
        origin.origin == "approved_llm"
        and origin.proposal_item_id == item_id
        and state.source == "manual"
    )
    assert origin.rule_id is None and origin.approval_receipt_id
    receipt = await db_session.get(FinanceCommandReceipt, origin.approval_receipt_id)
    assert receipt.response_json["grant"]["approved_by"] == str(owner)
    assert receipt.response_json["grant"]["target_category_id"] == str(target_id)
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(FinancialTransaction)
            .where(FinancialTransaction.id == txn_id)
        )
        == 1
    )


@pytest.mark.parametrize(
    "change",
    [
        "description",
        "taxonomy",
        "expiry",
        "manual",
        "target_archive",
        "deleted",
        "pending",
        "actual",
        "allocation",
    ],
)
async def test_stale_or_protected_proposal_never_writes_ledger(db_session, monkeypatch, change):
    owner, _, marker, target, txn, item = await proposed(db_session, monkeypatch)
    async with client_for(db_session, owner) as client:
        p = await preview(client, item)
        if change == "description":
            txn.description = "New description"
        if change == "taxonomy":
            from app.finance.models import Category

            db_session.add(Category(user_id=owner, name="Added unrelated category", type="expense"))
        if change == "expiry":
            item.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        if change == "manual":
            from tests.test_finance.test_categorization import (
                apply as manual_apply,
            )
            from tests.test_finance.test_categorization import (
                preview as manual_preview,
            )

            manual = await manual_preview(
                client, txn, [{"category_id": str(marker.id), "amount_minor": 10000}]
            )
            assert (await manual_apply(client, txn, manual)).status_code == 200
        if change == "target_archive":
            target.is_active = False
        if change == "deleted":
            from app.finance.service import delete_transaction

            await delete_transaction(db_session, owner, txn.id)
        if change == "pending":
            txn.is_pending = True
        if change == "actual":
            txn.source = "actual"
        if change == "allocation":
            # Real financial allocation fixture is covered by existing source guard;
            # source= document_payment alone is also outside autonomous allowlist.
            txn.source = "document_payment"
        await db_session.commit()
        if change != "deleted":
            before = sorted([columns(x) for x in txn.postings], key=lambda x: x["id"])
        result = await apply(client, item, p)
        assert result.status_code == 409, result.text
        if change != "deleted":
            await db_session.refresh(txn, ["postings"])
            assert sorted([columns(x) for x in txn.postings], key=lambda x: x["id"]) == before


async def test_new_category_is_readonly_and_reject_never_mutates_payment(db_session, monkeypatch):
    owner, _, _, _, txn, item = await proposed(db_session, monkeypatch, decision="new_category")
    before = sorted([columns(p) for p in txn.postings], key=lambda x: x["id"])
    async with client_for(db_session, owner) as client:
        row = (await client.get(f"{ROOT}/proposals/{item.id}")).json()
        assert row["new_category"]["name"] == "Nowa kategoria" and not row["eligible"]
        r = await client.post(f"{ROOT}/proposals/{item.id}/preview", json={"expected_version": 1})
        assert r.status_code == 422
        await db_session.refresh(item)
        key = uuid.uuid4().hex
        r = await mutate(
            client, "post", f"/proposals/{item.id}/reject", {"expected_version": 1}, key
        )
        assert r.status_code == 200 and r.json()["status"] == "rejected"
        assert (
            await mutate(
                client, "post", f"/proposals/{item.id}/reject", {"expected_version": 1}, key
            )
        ).json() == r.json()
    await db_session.refresh(txn, ["postings"])
    assert sorted([columns(p) for p in txn.postings], key=lambda x: x["id"]) == before


async def test_same_category_manual_confirmation_replaces_ai_origin(db_session, monkeypatch):
    from tests.test_finance.test_categorization import (
        apply as manual_apply,
    )
    from tests.test_finance.test_categorization import (
        preview as manual_preview,
    )

    owner, _, _, target, txn, item = await proposed(db_session, monkeypatch)
    async with client_for(db_session, owner) as client:
        p = await preview(client, item)
        result = await apply(client, item, p)
        assert result.status_code == 200, result.text
        v = result.json()["context"]["version"]
        p2 = await manual_preview(
            client, txn, [{"category_id": str(target.id), "amount_minor": 10000}]
        )
        r = await manual_apply(client, txn, p2)
        assert r.status_code == 200, r.text
        assert r.json()["version"] > v
        assert r.json()["assignment_origin"]["origin"] == "manual"
        assert r.json()["assignment_origin"]["proposal_item_id"] is None


async def test_apply_requires_true_and_forbids_target_amount_origin_override(
    db_session, monkeypatch
):
    owner, _, _, _, _, item = await proposed(db_session, monkeypatch)
    async with client_for(db_session, owner) as client:
        p = await preview(client, item)
        for extra in (
            {"confirmed": False},
            {"confirmed": 1},
            {"target_category_id": str(uuid.uuid4())},
            {"origin": "manual"},
            {"amount_minor": 1},
        ):
            r = await apply(client, item, p, **extra)
            assert r.status_code == 422, r.text


async def test_approval_audit_failure_rolls_back_receipt_state_origin_and_postings(
    db_session, monkeypatch
):
    from app.finance import proposals
    from app.finance.proposal_schemas import ProposalApply
    from app.finance.rule_models import TransactionCategorizationOrigin as Origin

    owner, _, _, _, txn, item = await proposed(db_session, monkeypatch)
    txn_id, item_id = txn.id, item.id
    before = [columns(x) for x in txn.postings]
    async with client_for(db_session, owner) as client:
        p = await preview(client, item)
    await db_session.commit()

    async def fail(*args, **kwargs):
        raise RuntimeError("Synthetic audit failure")

    monkeypatch.setattr(proposals, "log_event", fail)
    with pytest.raises(RuntimeError):
        await proposals.apply_proposal(
            db_session,
            owner,
            item_id,
            ProposalApply(
                expected_version=1, preview_snapshot=p["preview_snapshot"], confirmed=True
            ),
            idempotency_key="rollback-test",
        )
    await db_session.rollback()
    assert await db_session.scalar(select(Origin.id).where(Origin.transaction_id == txn_id)) is None
    assert (
        await db_session.scalar(
            select(TransactionCategorizationState.id).where(
                TransactionCategorizationState.transaction_id == txn_id
            )
        )
        is None
    )
    assert (
        await db_session.scalar(
            select(FinanceCommandReceipt.id).where(FinanceCommandReceipt.key == "rollback-test")
        )
        is None
    )
    fresh = await db_session.get(Item, item_id)
    assert fresh.status == "pending" and fresh.version == 1
    rows = (
        await db_session.scalars(
            select(Posting).where(Posting.transaction_id == txn_id).order_by(Posting.id)
        )
    ).all()
    assert sorted([columns(p) for p in rows], key=lambda p: p["id"]) == sorted(
        before, key=lambda p: p["id"]
    )


async def test_page_query_count_is_bounded_and_cursor_has_no_duplicates(db_session, monkeypatch):
    from app.finance import suggestion_worker
    from tests.test_finance.test_rule_events import new_expense

    owner, account, marker, _, _, _first = await proposed(db_session, monkeypatch)
    for description in ("Second", "Third"):
        txn = await new_expense(db_session, owner, account, marker, description)
        await db_session.commit()
        job = await job_for(db_session, txn)
        assert await suggestion_worker.process_suggestion_job({}, str(job.id)) == "completed"
    queries = []

    def record(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    async with client_for(db_session, owner) as client:
        event.listen(db_session.bind.sync_engine, "before_cursor_execute", record)
        try:
            page = await client.get(ROOT + "/proposals?limit=1")
            assert page.status_code == 200, page.text
            one_count = len(queries)
            cursor = page.json()["next_cursor"]
            assert cursor
            next_page = await client.get(ROOT + "/proposals", params={"cursor": cursor, "limit": 1})
            assert next_page.status_code == 200, next_page.text
            assert next_page.json()["items"][0]["id"] != page.json()["items"][0]["id"]
            queries.clear()
            all_page = await client.get(ROOT + "/proposals?limit=1000")
            assert all_page.status_code == 200, all_page.text
            assert all_page.json()["page_size"] == 20 and len(all_page.json()["items"]) == 3
            assert len(queries) <= one_count + 2 and len(queries) <= 20
            assert (await client.get(ROOT + "/proposals?cursor=e30=")).status_code == 422
        finally:
            event.remove(db_session.bind.sync_engine, "before_cursor_execute", record)


async def test_category_referenced_only_by_proposal_cannot_be_deleted(db_session, monkeypatch):
    owner, _, _, target, _, _ = await proposed(db_session, monkeypatch)
    async with client_for(db_session, owner) as client:
        r = await client.delete(f"/api/finance/categories/{target.id}")
        assert r.status_code == 409, r.text


async def test_proposal_commands_require_real_csrf(db_session, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.config import settings
    from app.database import get_db
    from app.identity.service import create_session
    from app.main import app

    owner, _, _, _, _, item = await proposed(db_session, monkeypatch)
    token, csrf, _ = await create_session(db_session, owner)
    await db_session.commit()
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "_trusted_origins", ("https://ui.test.invalid",))

    async def database():
        yield db_session

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://ui.test.invalid"
        ) as client:
            headers = {
                "Origin": "https://ui.test.invalid",
                "Cookie": f"advisor_session={token}; advisor_csrf={csrf}",
                "Idempotency-Key": "csrf-proposals",
            }
            for action in ("preview", "apply", "reject"):
                r = await client.post(
                    f"{ROOT}/proposals/{item.id}/{action}", headers=headers, json={}
                )
                assert r.status_code == 403, r.text
            r = await client.post(
                f"{ROOT}/proposals/{item.id}/preview",
                headers={**headers, "X-CSRF-Token": csrf},
                json={"expected_version": 1},
            )
            assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.clear()


async def test_expiry_only_changes_proposal_metadata_and_foreign_source_never_leaks(
    db_session, monkeypatch
):
    from app.finance.proposal_state import expire_proposal_items
    from tests.test_finance.test_categorization import setup as other_setup

    owner, _, _, _, txn, item = await proposed(db_session, monkeypatch)
    before = columns(txn)
    item.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    assert await expire_proposal_items(db_session, datetime.now(UTC), limit=20) == 1
    await db_session.commit()
    assert item.status == "expired" and item.version == 2
    assert columns(txn) == before
    _, foreign, _, _, _ = await other_setup(db_session)
    item.transaction_id = foreign.id
    await db_session.commit()
    async with client_for(db_session, owner) as client:
        r = await client.get(f"{ROOT}/proposals/{item.id}")
        assert r.status_code == 200, r.text
        assert r.json()["transaction_id"] is None and r.json()["amount_minor"] is None
        assert r.json()["blocked_reason"] == "source_missing"


@pytest.mark.parametrize("first_operation", ["ai", "manual"])
async def test_manual_confirmation_and_review_apply_serialize_in_both_orders(
    db_session, monkeypatch, first_operation
):
    import asyncio

    from sqlalchemy import text

    from app.finance.categorization import apply_categorization
    from app.finance.categorization_context import CategorizationError
    from app.finance.categorization_schemas import CategorizationApply
    from app.finance.proposal_schemas import ProposalApply
    from app.finance.proposals import apply_proposal
    from tests.test_finance.test_categorization import preview as manual_preview
    from tests.test_finance.test_categorization_races import wait_for_database_lock

    owner, _, marker, target, txn, item = await proposed(db_session, monkeypatch)
    proposal_id, txn_id, marker_id, target_id = item.id, txn.id, marker.id, target.id
    async with client_for(db_session, owner) as client:
        p = await preview(client, item)
        m = await manual_preview(
            client, txn, [{"category_id": str(marker_id), "amount_minor": 10000}]
        )
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    ready, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    outcomes = {}
    pids = []

    async def operation(db, what):
        try:
            if what == "ai":
                await apply_proposal(
                    db,
                    owner,
                    proposal_id,
                    ProposalApply(
                        expected_version=1, preview_snapshot=p["preview_snapshot"], confirmed=True
                    ),
                    idempotency_key="race-ai",
                )
            else:
                await apply_categorization(
                    db,
                    owner,
                    txn_id,
                    CategorizationApply(
                        expected_version=m["expected_version"],
                        expected_preview_snapshot=m["preview_snapshot"],
                        parts=m["after_parts"],
                        confirmed=True,
                    ),
                    idempotency_key="race-manual",
                )
            outcomes[what] = "applied"
        except CategorizationError:
            outcomes[what] = "conflict"
            await db.rollback()

    async def first():
        async with sessions() as db:
            await operation(db, first_operation)
            ready.set()
            await release.wait()
            await db.commit()

    async def second():
        await ready.wait()
        async with sessions() as db:
            pids.append(await db.scalar(text("SELECT pg_backend_pid()")))
            waiting.set()
            await operation(db, "manual" if first_operation == "ai" else "ai")
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
    assert outcomes[first_operation] == "applied"
    assert outcomes["manual" if first_operation == "ai" else "ai"] == "conflict"
    cat = await db_session.scalar(
        select(Posting.category_id).where(
            Posting.transaction_id == txn_id, Posting.category_id.is_not(None)
        )
    )
    assert cat == (target_id if first_operation == "ai" else marker_id)


async def test_fresh_account_history_search_list_detail_preserve_ai_human_lineage(
    db_session, monkeypatch
):
    owner, account, _, _, txn, item = await proposed(db_session, monkeypatch)
    txn_id, account_id, item_id = txn.id, account.id, item.id
    async with client_for(db_session, owner) as client:
        p = await preview(client, item)
        assert (await apply(client, item, p)).status_code == 200
    db_session.expunge_all()
    async with client_for(db_session, owner) as client:
        for path in (
            f"/api/finance/accounts/{account_id}/transactions",
            "/api/finance/transactions/search",
            "/api/finance/transactions?year=2026&month=2",
            f"/api/finance/transactions/{txn_id}",
        ):
            response = await client.get(path)
            assert response.status_code == 200, response.text
            data = response.json()
            row = (
                data
                if path.endswith(str(txn_id))
                else next(
                    r
                    for r in (data["items"] if isinstance(data, dict) else data)
                    if r["id"] == str(txn_id)
                )
            )
            assert row["assignment_origin"]["origin"] == "approved_llm"
            assert row["assignment_origin"]["proposal_item_id"] == str(item_id)
