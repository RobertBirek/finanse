"""Real PostgreSQL lock admission decides; in-memory previews never decide a write."""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.finance.categorization_context import CategorizationError
from app.finance.models import DocumentPaymentAllocation, FinancialTransaction
from app.finance.receipt_approval import approve_receipt_items
from app.finance.receipt_items import save_receipt_draft
from app.finance.receipt_payment import apply_receipt_payment
from app.finance.receipt_schemas import (
    ReceiptDraftSave,
    ReceiptItemsApprove,
    ReceiptPaymentApply,
    ReceiptStoreChange,
)
from tests.test_finance.receipt_helpers import payload
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_categorization_races import wait_for_database_lock
from tests.test_finance.test_receipt_payment import payment_ready, preview

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize(
    "kind",
    ["draft", "approve", "store", "category", "bill_total", "unlink", "manual", "attach_source"],
)
@pytest.mark.parametrize("first_operation", ["apply", "other"])
async def test_receipt_apply_serializes_with_source_changes(db_session, kind, first_operation):
    from app.documents.models import Document
    from app.finance.bill_payments import unlink_payment
    from app.finance.bills import attach_source, update_bill
    from app.finance.bills_schemas import BillUpdate, MutationContext
    from app.finance.categorization import apply_categorization
    from app.finance.categorization_schemas import CategorizationApply
    from app.finance.entities import update_category
    from app.finance.receipt_stores import change_receipt_store
    from app.finance.schemas import CategoryUpdate
    from tests.test_finance.test_categorization import preview as manual_preview

    owner, bill, txn, _, marker, food, home, approved, store = await payment_ready(db_session)
    bill_id, txn_id, food_id, bill_version = bill.id, txn.id, food.id, bill.version
    body = payload(food, home, store)
    allocation_id = await db_session.scalar(select(DocumentPaymentAllocation.id))
    doc = Document(
        user_id=owner,
        filename="synthetic.txt",
        original_name="synthetic.txt",
        mime_type="text/plain",
        size_bytes=1,
        storage_path="/synthetic/not-read.txt",
        sha256_hash=uuid.uuid4().hex * 2,
        status="processed",
    )
    db_session.add(doc)
    await db_session.commit()
    doc_id = doc.id
    async with client_for(db_session, owner) as client:
        p = await preview(client, bill_id, approved)
        manual = await manual_preview(
            client, txn, [{"category_id": str(marker.id), "amount_minor": 9000}]
        )
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    admitted, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids = []
    outcomes = {}

    async def operation(db, which):
        try:
            if which == "apply":
                await apply_receipt_payment(
                    db,
                    owner,
                    bill_id,
                    ReceiptPaymentApply(
                        expected_state_version=2,
                        approved_revision_id=p["approved_revision_id"],
                        expected_preview_snapshot=p["preview_snapshot"],
                        confirmed=True,
                    ),
                    idempotency_key="race-apply",
                )
            elif kind in {"draft", "approve"}:
                result = await save_receipt_draft(
                    db,
                    owner,
                    bill_id,
                    ReceiptDraftSave(
                        expected_version=2, expected_bill_version=bill_version, body=body
                    ),
                    idempotency_key="race-draft",
                )
                if kind == "approve":
                    await approve_receipt_items(
                        db,
                        owner,
                        bill_id,
                        ReceiptItemsApprove(
                            expected_version=result.state_version,
                            draft_revision_id=result.draft.id,
                            expected_body_sha256=result.draft.body_sha256,
                            confirmed=True,
                        ),
                        idempotency_key="race-approve",
                    )
            elif kind == "store":
                await change_receipt_store(
                    db,
                    owner,
                    uuid.UUID(store["id"]),
                    ReceiptStoreChange(expected_version=1, active=False),
                    idempotency_key="race-store",
                )
            elif kind == "category":
                await update_category(db, owner, food_id, CategoryUpdate(is_active=False))
            elif kind == "bill_total":
                await update_bill(
                    db,
                    owner,
                    bill_id,
                    BillUpdate(expected_version=bill_version, total_minor=9001),
                    context=MutationContext(idempotency_key="race-header"),
                )
            elif kind == "unlink":
                await unlink_payment(
                    db,
                    owner,
                    bill_id,
                    allocation_id,
                    bill_version,
                    context=MutationContext(idempotency_key="race-unlink"),
                )
            elif kind == "attach_source":
                await attach_source(
                    db,
                    owner,
                    bill_id,
                    doc_id,
                    bill_version,
                    context=MutationContext(idempotency_key="race-attach"),
                )
            else:
                await apply_categorization(
                    db,
                    owner,
                    txn_id,
                    CategorizationApply(
                        expected_version=manual["expected_version"],
                        expected_preview_snapshot=manual["preview_snapshot"],
                        parts=manual["after_parts"],
                        confirmed=True,
                    ),
                    idempotency_key="race-manual",
                )
            outcomes[which] = "applied"
        except (CategorizationError, RuntimeError) as error:
            outcomes[which] = "conflict"
            await db.rollback()
            if which == first_operation:
                raise AssertionError("First admission unexpectedly conflicted") from error

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
            await operation(db, "other" if first_operation == "apply" else "apply")
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
    if first_operation == "other":
        assert outcomes["apply"] == "conflict"
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 1


@pytest.mark.parametrize("same_key", [True, False])
async def test_two_apply_commands_one_write_under_real_database_lock(db_session, same_key):
    from app.finance.models import FinanceCommandReceipt

    owner, bill, _, _, _, _, _, approved, _ = await payment_ready(db_session)
    bill_id = bill.id
    async with client_for(db_session, owner) as client:
        p = await preview(client, bill_id, approved)
    await db_session.commit()
    data = ReceiptPaymentApply(
        expected_state_version=2,
        approved_revision_id=p["approved_revision_id"],
        expected_preview_snapshot=p["preview_snapshot"],
        confirmed=True,
    )
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    admitted, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids = []
    results = []

    async def first():
        async with sessions() as db:
            results.append(
                (
                    await apply_receipt_payment(db, owner, bill_id, data, idempotency_key="first")
                ).model_dump(mode="json")
            )
            admitted.set()
            await release.wait()
            await db.commit()

    async def second():
        await admitted.wait()
        async with sessions() as db:
            pids.append(await db.scalar(text("SELECT pg_backend_pid()")))
            waiting.set()
            try:
                results.append(
                    (
                        await apply_receipt_payment(
                            db,
                            owner,
                            bill_id,
                            data,
                            idempotency_key="first" if same_key else "second",
                        )
                    ).model_dump(mode="json")
                )
                await db.commit()
            except CategorizationError:
                results.append("conflict")
                await db.rollback()

    a, b = asyncio.create_task(first()), asyncio.create_task(second())
    try:
        await asyncio.wait_for(waiting.wait(), 10)
        await wait_for_database_lock(db_session, pids[0])
        assert not b.done()
    finally:
        release.set()
        await asyncio.wait_for(asyncio.gather(a, b), 15)
    assert results[1] == (results[0] if same_key else "conflict")
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(FinanceCommandReceipt)
            .where(FinanceCommandReceipt.action == "apply_receipt_item_split")
        )
        == 1
    )


@pytest.mark.parametrize("kind", ["archive", "new_approval"])
@pytest.mark.parametrize("first_operation", ["target", "source"])
async def test_hint_source_change_serializes_with_target_approval(
    db_session, kind, first_operation
):
    from app.finance.bills import set_bill_lifecycle
    from app.finance.bills_schemas import MutationContext
    from app.finance.receipt_context import load_receipt_context
    from tests.test_finance.receipt_helpers import ready, save, store_for
    from tests.test_finance.test_receipt_history import history, other_bill, source_ready

    owner, source, _, _, _, food, home = await ready(db_session)
    source_id, source_version = source.id, source.version
    async with client_for(db_session, owner) as client:
        store = await store_for(client)
        await source_ready(db_session, client, source, food, home, store)
        target = await other_bill(db_session, owner)
        target_id = target.id
        ref = (await history(client, target, store, "MLEKO 2%"))["items"][0]["ref"]
        body = payload(food, home, store)
        body["lines"][0]["hint"] = ref
        draft = await save(client, target, body)
    target_input = ReceiptItemsApprove(
        expected_version=1,
        draft_revision_id=draft["draft"]["id"],
        expected_body_sha256=draft["draft"]["body_sha256"],
        confirmed=True,
    )
    source_body = payload(home, food, store)
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    admitted, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids = []
    outcomes = {}

    async def operate(db, which):
        try:
            if which == "target":
                await approve_receipt_items(
                    db, owner, target_id, target_input, idempotency_key="target-approve"
                )
            elif kind == "archive":
                await set_bill_lifecycle(
                    db,
                    owner,
                    source_id,
                    "archived",
                    source_version,
                    context=MutationContext(idempotency_key="source-archive"),
                )
            else:
                d = await save_receipt_draft(
                    db,
                    owner,
                    source_id,
                    ReceiptDraftSave(
                        expected_version=2, expected_bill_version=source_version, body=source_body
                    ),
                    idempotency_key="source-draft",
                )
                await approve_receipt_items(
                    db,
                    owner,
                    source_id,
                    ReceiptItemsApprove(
                        expected_version=3,
                        draft_revision_id=d.draft.id,
                        expected_body_sha256=d.draft.body_sha256,
                        confirmed=True,
                    ),
                    idempotency_key="source-approve",
                )
            outcomes[which] = "applied"
        except CategorizationError:
            outcomes[which] = "conflict"
            await db.rollback()

    async def first():
        async with sessions() as db:
            await operate(db, first_operation)
            admitted.set()
            await release.wait()
            await db.commit()

    async def second():
        await admitted.wait()
        async with sessions() as db:
            pids.append(await db.scalar(text("SELECT pg_backend_pid()")))
            waiting.set()
            await operate(db, "source" if first_operation == "target" else "target")
            await db.commit()

    a, b = asyncio.create_task(first()), asyncio.create_task(second())
    try:
        await asyncio.wait_for(waiting.wait(), 10)
        await wait_for_database_lock(db_session, pids[0])
        assert not b.done()
    finally:
        release.set()
        await asyncio.wait_for(asyncio.gather(a, b), 15)
    assert outcomes["source"] == "applied"
    assert outcomes["target"] == ("applied" if first_operation == "target" else "conflict")
    ctx = await load_receipt_context(db_session, owner, target_id)
    assert bool(ctx.approved) == (first_operation == "target")
    assert bool(ctx.draft) == (first_operation == "source")
    if ctx.approved:
        assert ctx.approved.current and ctx.approved.body.lines[
            0
        ].hint.source_revision_id == uuid.UUID(ref["source_revision_id"])
