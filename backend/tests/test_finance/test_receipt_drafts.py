import uuid

import pytest
from sqlalchemy import func, select

from app.finance.models import FinanceCommandReceipt, Posting
from app.finance.receipt_models import ReceiptItemRevision, ReceiptItemState
from tests.test_finance.receipt_helpers import ROOT, mutate, payload, ready, save, store_for
from tests.test_finance.test_account_currency import client_for

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_context_get_creates_no_rows(db_session):
    owner, bill, _, _, _, _, _ = await ready(db_session)
    before = await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt))
    async with client_for(db_session, owner) as client:
        r = await client.get(f"{ROOT}/bills/{bill.id}/items")
        assert r.status_code == 200, r.text
        assert r.json()["state_version"] == 0 and r.json()["draft"] is None and r.json()["editable"]
    assert await db_session.scalar(select(func.count()).select_from(ReceiptItemState)) == 0
    assert (
        await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == before
    )


async def test_first_save_appends_draft_and_replay_returns_same_revision(db_session):
    owner, bill, _, _, _, food, home = await ready(db_session)
    count = await db_session.scalar(select(func.count()).select_from(Posting))
    async with client_for(db_session, owner) as client:
        store = await store_for(client)
        body = payload(food, home, store)
        key = uuid.uuid4().hex
        request = {"expected_version": 0, "expected_bill_version": bill.version, "body": body}
        r = await mutate(client, f"/bills/{bill.id}/items/draft", request, key=key)
        assert r.status_code == 200, r.text
        assert r.json()["state_version"] == 1 and r.json()["calculation"]["net_total_minor"] == 9000
        again = await mutate(client, f"/bills/{bill.id}/items/draft", request, key=key)
        assert again.json() == r.json()
        conflict = await mutate(
            client, f"/bills/{bill.id}/items/draft", {**request, "expected_version": 1}, key=key
        )
        assert conflict.status_code == 409
    assert await db_session.scalar(select(func.count()).select_from(ReceiptItemRevision)) == 1
    assert await db_session.scalar(select(func.count()).select_from(Posting)) == count


async def test_second_save_preserves_old_rows_and_discard_keeps_all_evidence(db_session):
    owner, bill, _, _, _, food, home = await ready(db_session)
    async with client_for(db_session, owner) as client:
        body = payload(food, home)
        first = await save(client, bill, body)
        body["lines"][0]["name"] = "Poprawiona nazwa"
        second = await save(client, bill, body, 1)
        assert second["draft"]["id"] != first["draft"]["id"] and second["state_version"] == 2
        r = await mutate(client, f"/bills/{bill.id}/items/discard-draft", {"expected_version": 2})
        assert r.status_code == 200 and r.json()["draft"] is None and r.json()["state_version"] == 3
    assert await db_session.scalar(select(func.count()).select_from(ReceiptItemRevision)) == 2


async def test_incomplete_can_save_but_structurally_dangling_share_cannot(db_session):
    owner, bill, _, _, _, food, home = await ready(db_session)
    async with client_for(db_session, owner) as client:
        body = payload(food, home)
        body["lines"][0]["amount_minor"] = None
        r = await save(client, bill, body)
        assert r["calculation"]["net_total_minor"] is None and r["calculation"]["problems"]
        body["lines"].pop(0)
        r = await mutate(
            client,
            f"/bills/{bill.id}/items/draft",
            {"expected_version": 1, "expected_bill_version": bill.version, "body": body},
        )
        assert r.status_code == 422


async def test_store_duplicate_reference_archive_and_deleted_receipt_replay(db_session):
    owner, bill, _, _, _, food, home = await ready(db_session)
    async with client_for(db_session, owner) as client:
        store = await store_for(client)
        r = await mutate(client, "/receipt-stores", {"name": "  SKLEP  OSIEDLOWY "})
        assert r.status_code == 409
        await save(client, bill, payload(food, home, store))
        r = await mutate(
            client, f"/receipt-stores/{store['id']}", {"expected_version": 1}, method="delete"
        )
        assert r.status_code == 409
        r = await mutate(
            client,
            f"/receipt-stores/{store['id']}",
            {"expected_version": 1, "active": False},
            method="patch",
        )
        assert r.status_code == 200
        assert (await client.get(ROOT + "/receipt-stores")).json()["items"] == []
        assert (
            len((await client.get(ROOT + "/receipt-stores?include_inactive=true")).json()["items"])
            == 1
        )
        unused = await store_for(client, "Inny")
        key = uuid.uuid4().hex
        r = await mutate(
            client,
            f"/receipt-stores/{unused['id']}",
            {"expected_version": 1},
            method="delete",
            key=key,
        )
        assert r.status_code == 200
        assert (
            await mutate(
                client,
                f"/receipt-stores/{unused['id']}",
                {"expected_version": 1},
                method="delete",
                key=key,
            )
        ).json() == r.json()


async def test_foreign_bill_and_category_are_not_allowed(db_session):
    owner, bill, _, _, _, food, home = await ready(db_session)
    _other, other_bill, _, _, _, foreign, _ = await ready(db_session)
    async with client_for(db_session, owner) as client:
        assert (await client.get(f"{ROOT}/bills/{other_bill.id}/items")).status_code == 404
        body = payload(food, home)
        body["lines"][0]["category_id"] = str(foreign.id)
        r = await mutate(
            client,
            f"/bills/{bill.id}/items/draft",
            {"expected_version": 0, "expected_bill_version": bill.version, "body": body},
        )
        assert r.status_code == 404


async def test_category_referenced_only_by_item_has_controlled_delete_conflict(db_session):
    owner, bill, _, _, _, food, home = await ready(db_session)
    async with client_for(db_session, owner) as client:
        await save(client, bill, payload(food, home))
        r = await client.delete(f"{ROOT}/categories/{food.id}")
        assert r.status_code == 409, r.text


async def test_store_pagination_can_enumerate_all_and_rejects_bad_cursor(db_session, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "FINANCE_RECEIPT_STORE_PAGE_SIZE", 1)
    owner, _, _, _, _, _, _ = await ready(db_session)
    async with client_for(db_session, owner) as client:
        await store_for(client, "A")
        await store_for(client, "B")
        first = (await client.get(ROOT + "/receipt-stores")).json()
        second = (
            await client.get(ROOT + "/receipt-stores", params={"cursor": first["next_cursor"]})
        ).json()
        assert (
            first["items"][0]["name"] == "A"
            and second["items"][0]["name"] == "B"
            and second["next_cursor"] is None
        )
        assert (await client.get(ROOT + "/receipt-stores?cursor=e30=")).status_code == 422


async def test_receipt_mutations_require_real_session_csrf(db_session, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.config import settings
    from app.database import get_db
    from app.identity.service import create_session
    from app.main import app

    owner, bill, _, _, _, _, _ = await ready(db_session)
    token, csrf, _ = await create_session(db_session, owner)
    await db_session.commit()
    bill_id = str(bill.id)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "_trusted_origins", ("https://ui.test.invalid",))

    async def database():
        yield db_session

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://ui.test.invalid"
        ) as client:
            common = {
                "Origin": "https://ui.test.invalid",
                "Cookie": f"advisor_session={token}; advisor_csrf={csrf}",
                "Idempotency-Key": "csrf",
            }
            for path in [
                "/receipt-stores",
                f"/bills/{bill_id}/items/draft",
                f"/bills/{bill_id}/items/discard-draft",
                f"/bills/{bill_id}/items/approve",
                f"/bills/{bill_id}/items/payment-apply",
                f"/bills/{bill_id}/items/payment-preview",
            ]:
                assert (await client.post(ROOT + path, headers=common, json={})).status_code == 403
            r = await client.post(
                ROOT + "/receipt-stores",
                headers={**common, "X-CSRF-Token": csrf},
                json={"name": "Własny sklep"},
            )
            assert r.status_code == 200, r.text
            assert (await client.get(ROOT + f"/bills/{bill_id}/items")).status_code == 401
    finally:
        app.dependency_overrides.clear()


async def test_tightened_input_limits_do_not_make_saved_history_or_replay_unreadable(
    db_session, monkeypatch
):
    from app.config import settings

    owner, bill, _, _, _, food, home = await ready(db_session)
    bill_id = bill.id
    async with client_for(db_session, owner) as client:
        body = payload(food, home)
        key = uuid.uuid4().hex
        request = {"expected_version": 0, "expected_bill_version": bill.version, "body": body}
        first = await mutate(client, f"/bills/{bill_id}/items/draft", request, key=key)
        assert first.status_code == 200, first.text
        monkeypatch.setattr(settings, "FINANCE_RECEIPT_MAX_LINES", 1)
        monkeypatch.setattr(settings, "FINANCE_RECEIPT_ITEM_NAME_MAX_CHARS", 3)
        read = await client.get(f"{ROOT}/bills/{bill_id}/items")
        assert read.status_code == 200, read.text
        assert len(read.json()["draft"]["body"]["lines"]) == 2
        replay = await mutate(client, f"/bills/{bill_id}/items/draft", request, key=key)
        assert replay.status_code == 200 and replay.json() == first.json(), replay.text
        new = await mutate(
            client, f"/bills/{bill_id}/items/draft", {**request, "expected_version": 1}
        )
        assert new.status_code == 422, new.text
