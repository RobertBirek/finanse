import uuid

import pytest

from app.finance.models import FinancialDocument
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


async def source_ready(db, client, bill, food, home, store, *, name="MLEKO 2%"):
    body = payload(food, home, store)
    body["lines"][0]["name"] = name
    await approve_items(client, bill.id, await save(client, bill, body))


async def other_bill(db, owner):
    row = FinancialDocument(
        user_id=owner,
        kind="receipt",
        supplier_name="Sklep",
        description="Paragon",
        total_minor=9000,
        currency="PLN",
        review="approved",
    )
    db.add(row)
    await db.commit()
    return row


async def history(client, bill, store, name):
    r = await client.get(
        f"{ROOT}/bills/{bill.id}/items/history", params={"store_id": store["id"], "name": name}
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_first_purchase_has_no_hint_and_category_choices_remain(db_session):
    owner, bill, _, _, _, food, home = await ready(db_session)
    async with client_for(db_session, owner) as client:
        store = await store_for(client)
        h = await history(client, bill, store, "MLEKO 2%")
        assert h["items"] == [] and h["match_kind"] == "none" and not h["history_incomplete"]
        choices = (await client.get(f"{ROOT}/bills/{bill.id}/items")).json()[
            "eligible_category_ids"
        ]
        assert str(food.id) in choices and str(home.id) in choices


@pytest.mark.parametrize(
    "name,kind",
    [
        (" mleko   2% ", "exact"),
        ("MLEKO", "prefix"),
        ("MLEKO 3,2%", "none"),
        ("%", "none"),
        ("_", "none"),
    ],
)
async def test_exact_prefix_and_digits_are_shop_scoped_and_never_autoapply(db_session, name, kind):
    owner, bill, _, _, _, food, home = await ready(db_session)
    async with client_for(db_session, owner) as client:
        store = await store_for(client)
        await source_ready(db_session, client, bill, food, home, store)
        target = await other_bill(db_session, owner)
        h = await history(client, target, store, name)
        assert h["match_kind"] == kind
        assert bool(h["items"]) == (kind != "none")
        if h["items"]:
            assert h["items"][0]["ref"]["category_id"] == str(food.id)
        assert (await history(client, bill, store, name))["items"] == []
        other = await store_for(client, "Drugi sklep")
        assert (await history(client, target, other, name))["items"] == []


async def test_conflicting_exact_names_never_pick_latest_category(db_session):
    owner, bill, _, _, _, food, home = await ready(db_session)
    async with client_for(db_session, owner) as client:
        store = await store_for(client)
        await source_ready(db_session, client, bill, food, home, store)
        second = await other_bill(db_session, owner)
        await source_ready(db_session, client, second, home, food, store)
        target = await other_bill(db_session, owner)
        h = await history(client, target, store, "MLEKO 2%")
        assert h["conflict"] and {i["ref"]["category_id"] for i in h["items"]} == {
            str(food.id),
            str(home.id),
        }


async def test_stale_hint_is_rejected_before_target_approval_and_archived_source_not_suggested(
    db_session,
):
    owner, bill, _, _, _, food, home = await ready(db_session)
    async with client_for(db_session, owner) as client:
        store = await store_for(client)
        await source_ready(db_session, client, bill, food, home, store)
        target = await other_bill(db_session, owner)
        hint = (await history(client, target, store, "MLEKO 2%"))["items"][0]["ref"]
        body = payload(food, home, store)
        body["lines"][0]["hint"] = hint
        draft = await save(client, target, body)
        bill.lifecycle = "archived"
        bill.version += 1
        await db_session.commit()
        r = await mutate(
            client,
            f"/bills/{target.id}/items/approve",
            {
                "expected_version": 1,
                "draft_revision_id": draft["draft"]["id"],
                "expected_body_sha256": draft["draft"]["body_sha256"],
                "confirmed": True,
            },
        )
        assert r.status_code == 409, r.text


@pytest.mark.parametrize("count", [1, 200])
async def test_history_queries_are_bounded_and_scan_cap_is_truthful(db_session, monkeypatch, count):
    from sqlalchemy import event

    from app.config import settings

    owner, bill, _, _, _, food, _ = await ready(db_session)
    async with client_for(db_session, owner) as client:
        store = await store_for(client)
        body = {
            "store_id": store["id"],
            "store_version": 1,
            "lines": [
                {
                    "line_key": str(uuid.uuid4()),
                    "name": "MLEKO",
                    "amount_minor": 9000 // count,
                    "category_id": str(food.id),
                }
                for _ in range(count)
            ],
            "discounts": [],
        }
        await approve_items(client, bill.id, await save(client, bill, body))
        target = await other_bill(db_session, owner)
        monkeypatch.setattr(settings, "FINANCE_RECEIPT_HISTORY_SCAN_LIMIT", 2)
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(db_session.bind.sync_engine, "before_cursor_execute", record)
        try:
            h = await history(client, target, store, "MLEKO")
        finally:
            event.remove(db_session.bind.sync_engine, "before_cursor_execute", record)
        assert len(statements) <= 12
        assert h["history_incomplete"] == (count > 2) and h["has_more"] == (count > 2)
        assert len(h["items"]) == min(count, 2)


async def test_approved_target_keeps_evidence_after_source_archived(db_session):
    owner, bill, _, _, _, food, home = await ready(db_session)
    async with client_for(db_session, owner) as client:
        store = await store_for(client)
        await source_ready(db_session, client, bill, food, home, store)
        target = await other_bill(db_session, owner)
        hint = (await history(client, target, store, "MLEKO 2%"))["items"][0]["ref"]
        body = payload(food, home, store)
        body["lines"][0]["hint"] = hint
        approved = await approve_items(client, target.id, await save(client, target, body))
        bill.lifecycle = "archived"
        await db_session.commit()
        response = (await client.get(f"{ROOT}/bills/{target.id}/items")).json()
        assert (
            response["approved"]["current"]
            and response["approved"]["body"]["lines"][0]["hint"] == hint
        )
        assert response["approved"]["id"] == approved["approved"]["id"]
