import uuid

import pytest
from sqlalchemy import func, select

from app.finance.models import DocumentPaymentAllocation, Posting
from app.finance.receipt_models import ReceiptItemRevision
from tests.test_finance.receipt_helpers import (
    ROOT,
    approve_items,
    mutate,
    payload,
    ready,
    save,
    store_for,
)
from tests.test_finance.test_account_currency import client_for

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_approval_creates_9000_evidence_only_and_new_draft_preserves_approved(db_session):
    owner, bill, _txn, _, _, food, home = await ready(db_session)
    before = await db_session.scalar(select(func.count()).select_from(Posting))
    async with client_for(db_session, owner) as client:
        store = await store_for(client)
        draft = await save(client, bill, payload(food, home, store))
        key = uuid.uuid4().hex
        approved = await approve_items(client, bill.id, draft, key)
        assert (
            approved["draft"] is None
            and approved["approved"]["current"]
            and approved["state_version"] == 2
        )
        assert (await approve_items(client, bill.id, draft, key)) == approved
        new = await save(client, bill, payload(food, home, store), 2)
        assert new["approved"]["id"] == approved["approved"]["id"] and new["draft"] is not None
    assert await db_session.scalar(select(func.count()).select_from(Posting)) == before
    assert await db_session.scalar(select(func.count()).select_from(DocumentPaymentAllocation)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ReceiptItemRevision)) == 3


async def test_allocation_version_only_does_not_make_items_stale(db_session):
    owner, bill, txn, _, _, food, home = await ready(db_session)
    async with client_for(db_session, owner) as client:
        store = await store_for(client)
        draft = await save(client, bill, payload(food, home, store))
        await approve_items(client, bill.id, draft)
        bill.version += 1
        posting = next(p for p in txn.postings if p.account_id)
        db_session.add(
            DocumentPaymentAllocation(
                user_id=owner,
                financial_document_id=bill.id,
                posting_id=posting.id,
                amount_minor=9000,
            )
        )
        await db_session.commit()
        r = await client.get(f"{ROOT}/bills/{bill.id}/items")
        assert r.json()["approved"]["current"] is True, r.text


@pytest.mark.parametrize("kind", ["mismatch", "marker", "ancestor", "confirmed", "store", "hint"])
async def test_incomplete_or_protected_items_cannot_be_approved(db_session, kind):
    owner, bill, _, _, marker, food, home = await ready(db_session)
    async with client_for(db_session, owner) as client:
        store = await store_for(client)
        body = payload(food, home, store)
        if kind == "mismatch":
            body["lines"][0]["amount_minor"] = 7999
        if kind == "marker":
            body["lines"][0]["category_id"] = str(marker.id)
        if kind == "ancestor":
            food.parent_id = home.id
            home.is_active = False
            await db_session.commit()
        if kind == "hint":
            body["lines"][0]["hint"] = {
                "source_bill_id": str(uuid.uuid4()),
                "source_revision_id": str(uuid.uuid4()),
                "source_line_key": body["lines"][0]["line_key"],
                "category_id": str(food.id),
                "match_kind": "exact",
                "algorithm_version": "receipt-history-v1",
                "source_sha256": "a" * 64,
            }
        if kind == "hint":
            r = await mutate(
                client,
                f"/bills/{bill.id}/items/draft",
                {"expected_version": 0, "expected_bill_version": bill.version, "body": body},
            )
            assert r.status_code == 404
            return
        draft = await save(client, bill, body)
        if kind == "store":
            await mutate(
                client,
                f"/receipt-stores/{store['id']}",
                {"expected_version": 1, "active": False},
                method="patch",
            )
        r = await mutate(
            client,
            f"/bills/{bill.id}/items/approve",
            {
                "expected_version": 1,
                "draft_revision_id": draft["draft"]["id"],
                "expected_body_sha256": draft["draft"]["body_sha256"],
                "confirmed": 1 if kind == "confirmed" else True,
            },
        )
        assert r.status_code in {409, 422}, r.text
