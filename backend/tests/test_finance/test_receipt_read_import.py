"""Adopting a transcription appends a human draft, never financial approval or payment."""

import copy
import uuid

import pytest
from sqlalchemy import func, select, update

from app.documents.receipt_read_models import ReceiptReadExtraction
from app.finance.categorization_context import columns
from app.finance.models import (
    Account,
    DocumentPaymentAllocation,
    FinancialDocument,
    FinancialTransaction,
    Posting,
)
from app.finance.receipt_models import ReceiptItemRevision, ReceiptItemState
from app.finance.receipt_read_models import ReceiptReadLineage
from tests.test_documents.test_receipt_read_payload import payload_data
from tests.test_documents.test_receipt_read_worker import bounded_http, worker_ready
from tests.test_documents.test_vision_client import _response
from tests.test_finance.receipt_helpers import ROOT, approve_items, store_for
from tests.test_finance.receipt_read_helpers import read_path
from tests.test_finance.test_account_currency import client_for

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def accepted(db, monkeypatch, tmp_path, *, warning=False):
    from app.documents.receipt_read_worker import process_receipt_read

    r, job_id = await worker_ready(db, monkeypatch, tmp_path)
    data = payload_data()
    if warning:
        data["warnings"] = ["missing_rows"]
    bounded_http(monkeypatch, lambda req: _response(data))
    await process_receipt_read({}, str(job_id))
    return r, job_id


async def adopt(client, r, job_id, *, preview=None, key=None):
    if preview is None:
        current = (await client.get(f"{ROOT}/bills/{r.bill_id}/items")).json()
        p = await client.post(
            read_path(r, "read-import-preview"),
            json={"job_id": str(job_id), "expected_state_version": current["state_version"]},
        )
        assert p.status_code == 200, p.text
        preview = p.json()
    return await client.post(
        read_path(r, "read-import"),
        json={
            "job_id": str(job_id),
            "expected_state_version": preview["state_version"],
            "expected_import_snapshot": preview["import_snapshot"],
            "confirmed_replace": True,
        },
        headers={"Idempotency-Key": key or uuid.uuid4().hex},
    )


async def save_body(client, r, context, body, review=None):
    data = {
        "expected_version": context["state_version"],
        "expected_bill_version": context["bill_version"],
        "body": body,
    }
    if review is not None:
        data["extraction_review"] = review
    return await client.post(
        f"{ROOT}/bills/{r.bill_id}/items/draft",
        json=data,
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )


def review_for(context):
    evidence = context["draft"]["evidence"]
    return {
        "extraction_id": evidence["extraction_id"],
        "expected_extraction_sha256": evidence["extraction_sha256"],
        "acknowledged_problem_keys": [
            p["key"] for p in evidence["pending_problems"] if p["requires_ack"]
        ],
    }


async def test_import_preserves_approved_and_ledger_exactly(db_session, monkeypatch, tmp_path):
    r, job = await accepted(db_session, monkeypatch, tmp_path)
    async with client_for(db_session, r.owner) as client:
        store = await store_for(client)
        # A pre-existing manual approval and a later saved draft stay in history.
        body = {
            "store_id": store["id"],
            "store_version": store["version"],
            "lines": [
                {
                    "line_key": str(uuid.uuid4()),
                    "name": "Manual previous",
                    "amount_minor": 9000,
                    "category_id": str(r.food_id),
                }
            ],
            "discounts": [],
        }
        base = (await client.get(f"{ROOT}/bills/{r.bill_id}/items")).json()
        saved = await save_body(client, r, base, body)
        assert saved.status_code == 200, saved.text
        approved = await approve_items(client, r.bill_id, saved.json())
        saved = await save_body(client, r, approved, body)
        assert saved.status_code == 200, saved.text
        olddraft = saved.json()["draft"]["id"]
        oldapproved = approved["approved"]["id"]
        before = {
            t.__tablename__: [
                columns(x) for x in (await db_session.scalars(select(t).order_by(t.id))).all()
            ]
            for t in [
                FinancialDocument,
                Posting,
                DocumentPaymentAllocation,
                FinancialTransaction,
                Account,
            ]
        }
        response = await adopt(client, r, job, key="adopt-once")
        assert response.status_code == 200, response.text
        ctx = response.json()
        draft = ctx["draft"]
        newbody = draft["body"]
        assert (
            draft["id"] != olddraft
            and ctx["approved"]["id"] == oldapproved
            and ctx["state_version"] == 4
        )
        assert newbody["store_id"] == store["id"] and newbody["store_version"] == store["version"]
        assert [l["amount_minor"] for l in newbody["lines"]] == [8000, 2000]
        assert all(l["category_id"] is None and l["hint"] is None for l in newbody["lines"])
        assert {s["line_key"] for s in newbody["discounts"][0]["shares"]} == {
            l["line_key"] for l in newbody["lines"]
        }
        assert all(
            l["line_key"] not in {str(uuid.UUID(int=1)), str(uuid.UUID(int=2))}
            for l in newbody["lines"]
        )
        assert draft["evidence"]["extraction_id"] and len(draft["evidence"]["line_map"]) == 2
        after = {
            t.__tablename__: [
                columns(x) for x in (await db_session.scalars(select(t).order_by(t.id))).all()
            ]
            for t in [
                FinancialDocument,
                Posting,
                DocumentPaymentAllocation,
                FinancialTransaction,
                Account,
            ]
        }
        assert before == after
        assert await db_session.scalar(select(func.count()).select_from(ReceiptItemRevision)) == 4
        assert await db_session.scalar(select(func.count()).select_from(ReceiptReadLineage)) == 1


async def test_matching_sum_missing_rows_blocks_until_review(db_session, monkeypatch, tmp_path):
    r, job = await accepted(db_session, monkeypatch, tmp_path, warning=True)
    async with client_for(db_session, r.owner) as client:
        response = await adopt(client, r, job)
        assert response.status_code == 200, response.text
        ctx = response.json()
        body = copy.deepcopy(ctx["draft"]["body"])
        store = await store_for(client)
        body.update(store_id=store["id"], store_version=store["version"])
        for line, category in zip(body["lines"], [r.food_id, r.home_id], strict=True):
            line["category_id"] = str(category)
        saved = await save_body(client, r, ctx, body)
        assert saved.status_code == 200, saved.text
        ctx = saved.json()
        assert ctx["calculation"]["net_total_minor"] == 9000 and not ctx["draft"]["current"]
        response = await client.post(
            f"{ROOT}/bills/{r.bill_id}/items/approve",
            json={
                "expected_version": ctx["state_version"],
                "draft_revision_id": ctx["draft"]["id"],
                "expected_body_sha256": ctx["draft"]["body_sha256"],
                "confirmed": True,
            },
            headers={"Idempotency-Key": "unreviewed-approve"},
        )
        assert response.status_code == 422, response.text
        reviewed = await save_body(client, r, ctx, body, review_for(ctx))
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["draft"]["current"]
        approved = await approve_items(client, r.bill_id, reviewed.json())
        assert approved["approved"]["evidence"]["acknowledgements"]
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 1


async def test_manual_correction_retains_edited_source_evidence(db_session, monkeypatch, tmp_path):
    r, job = await accepted(db_session, monkeypatch, tmp_path, warning=True)
    async with client_for(db_session, r.owner) as client:
        response = await adopt(client, r, job)
        assert response.status_code == 200, response.text
        ctx = response.json()
        body = copy.deepcopy(ctx["draft"]["body"])
        key = body["lines"][0]["line_key"]
        original = copy.deepcopy(ctx["draft"]["evidence"]["line_map"][key])
        body["lines"][0]["amount_minor"] = 7999
        manual = str(uuid.uuid4())
        body["lines"].append(
            {"line_key": manual, "name": "Manual", "amount_minor": 1, "category_id": None}
        )
        result = await save_body(client, r, ctx, body, review_for(ctx))
        assert result.status_code == 200, result.text
        ctx = result.json()
        e = ctx["draft"]["evidence"]
        assert "amount_minor" in e["line_map"][key]["edited_fields"]
        assert e["line_map"][key]["original_field_sha256"] == original["original_field_sha256"]
        assert manual not in e["line_map"] and e["acknowledgements"]
        body["lines"][0]["name"] = "Manual renamed"
        saved = await save_body(client, r, ctx, body)
        assert saved.status_code == 200, saved.text
        assert saved.json()["draft"]["evidence"]["acknowledgements"] == {}
        assert any(
            p["code"] == "receipt_extraction_review_required"
            for p in saved.json()["draft"]["problems"]
        )


@pytest.mark.parametrize("change", ["detach", "archive", "state"])
async def test_import_stale_source_or_draft_conflicts_without_side_effect(
    db_session, monkeypatch, tmp_path, change
):
    from app.documents.models import Document
    from app.finance.models import FinancialDocumentSource

    r, job = await accepted(db_session, monkeypatch, tmp_path)
    async with client_for(db_session, r.owner) as client:
        response = await client.post(
            read_path(r, "read-import-preview"),
            json={"job_id": str(job), "expected_state_version": 0},
        )
        assert response.status_code == 200, response.text
        p = response.json()
        if change == "detach":
            link = await db_session.scalar(
                select(FinancialDocumentSource).where(
                    FinancialDocumentSource.document_id == r.document_id
                )
            )
            await db_session.delete(link)
        if change == "archive":
            await db_session.execute(
                update(Document)
                .where(Document.id == r.document_id)
                .values(archived_at=__import__("datetime").datetime.now(__import__("datetime").UTC))
            )
        if change == "state":
            response = await adopt(client, r, job, preview=p)
            assert response.status_code == 200, response.text
        await db_session.commit()
        response = await adopt(client, r, job, preview=p)
        assert response.status_code in {404, 409}, response.text
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadLineage)) == (
        1 if change == "state" else 0
    )


async def test_ready_result_after_policy_off_and_header_change_requires_fresh_review(
    db_session, monkeypatch, tmp_path
):
    from app.documents.receipt_read_policy import set_receipt_read_policy

    r, job = await accepted(db_session, monkeypatch, tmp_path)
    await set_receipt_read_policy(
        db_session, enabled=False, expected_epoch=1, config=None, performed_by="synthetic"
    )
    await db_session.execute(
        update(FinancialDocument)
        .where(FinancialDocument.id == r.bill_id)
        .values(description="Changed human header", version=2)
    )
    await db_session.commit()
    async with client_for(db_session, r.owner) as client:
        response = await adopt(client, r, job)
        assert response.status_code == 200, response.text
        evidence = response.json()["draft"]["evidence"]
        assert any(
            p["key"].startswith("context/header_changed/") and p["requires_ack"]
            for p in evidence["pending_problems"]
        )
    assert await db_session.scalar(select(func.count()).select_from(ReceiptReadExtraction)) == 1


async def test_import_replay_does_not_restore_old_draft_or_accept_bad_review(
    db_session, monkeypatch, tmp_path
):
    r, job = await accepted(db_session, monkeypatch, tmp_path, warning=True)
    async with client_for(db_session, r.owner) as client:
        response = await client.post(
            read_path(r, "read-import-preview"),
            json={"job_id": str(job), "expected_state_version": 0},
        )
        assert response.status_code == 200, response.text
        preview = response.json()
        response = await adopt(client, r, job, preview=preview, key="frozen-import")
        assert response.status_code == 200, response.text
        first = response.json()
        review = review_for(first)
        review["acknowledged_problem_keys"] = ["fake_context_allow"]
        result = await save_body(client, r, first, first["draft"]["body"], review)
        assert result.status_code == 422, result.text
        changed = copy.deepcopy(first["draft"]["body"])
        changed["lines"][0]["name"] = "Human correction"
        result = await save_body(client, r, first, changed)
        assert result.status_code == 200, result.text
        replay = await adopt(client, r, job, preview=preview, key="frozen-import")
        assert replay.status_code == 200 and replay.json() == first, replay.text
        canonical = (await client.get(f"{ROOT}/bills/{r.bill_id}/items")).json()
        assert canonical["draft"]["body"]["lines"][0]["name"] == "Human correction"


async def test_import_audit_failure_rolls_back_revision_lineage_and_receipt(
    db_session, monkeypatch, tmp_path
):
    from app.documents.receipt_read_schemas import (
        ReceiptReadImport,
        ReceiptReadImportPreviewRequest,
    )
    from app.finance import receipt_commands
    from app.finance.models import FinanceCommandReceipt
    from app.finance.receipt_read_import import import_receipt_read, preview_receipt_read_import

    r, job = await accepted(db_session, monkeypatch, tmp_path)
    preview = await preview_receipt_read_import(
        db_session,
        r.owner,
        r.bill_id,
        ReceiptReadImportPreviewRequest(job_id=job, expected_state_version=0),
    )
    await db_session.commit()
    before = await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt))
    await db_session.commit()

    async def failure(*args, **kw):
        raise RuntimeError("synthetic-audit-failure")

    monkeypatch.setattr(receipt_commands, "log_event", failure)
    with pytest.raises(RuntimeError, match="synthetic-audit"):
        await import_receipt_read(
            db_session,
            r.owner,
            r.bill_id,
            ReceiptReadImport(
                job_id=job,
                expected_state_version=0,
                expected_import_snapshot=preview.import_snapshot,
                confirmed_replace=True,
            ),
            idempotency_key="failed-audit",
        )
    await db_session.rollback()
    assert (
        await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == before
    )
    for table in [ReceiptItemRevision, ReceiptReadLineage, ReceiptItemState]:
        assert await db_session.scalar(select(func.count()).select_from(table)) == 0


async def test_legacy_manual_draft_receipt_replays_without_new_optional_field(
    db_session, monkeypatch
):
    from app.finance.categorization_context import digest
    from app.finance.models import FinanceCommandReceipt
    from app.finance.receipt_items import get_receipt_items
    from tests.test_finance.receipt_read_helpers import read_ready

    r = await read_ready(db_session, monkeypatch, enable=False)
    original = (await get_receipt_items(db_session, r.owner, r.bill_id)).model_dump(mode="json")
    original_body = {"store_id": None, "store_version": None, "lines": [], "discounts": []}
    data = {"expected_version": 0, "expected_bill_version": 1, "body": original_body}
    db_session.add(
        FinanceCommandReceipt(
            user_id=r.owner,
            action="save_receipt_draft",
            key="pre-4b",
            request_hash=digest({"bill_id": str(r.bill_id), **data}),
            response_json=original,
        )
    )
    await db_session.commit()
    async with client_for(db_session, r.owner) as client:
        result = await client.post(
            f"{ROOT}/bills/{r.bill_id}/items/draft",
            json=data,
            headers={"Idempotency-Key": "pre-4b"},
        )
        assert result.status_code == 200, result.text
        assert result.json()["state_version"] == 0
    assert await db_session.scalar(select(func.count()).select_from(ReceiptItemRevision)) == 0
