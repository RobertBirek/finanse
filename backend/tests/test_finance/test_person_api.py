"""Person routes inherit owner/auth/CSRF protections and never rewrite a payment."""

import uuid

import pytest

from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_people import gift, ledger, person

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_person_api_link_replay_history_and_unlink(db_session):
    owner, txn, _, _ = await gift(db_session)
    await person(db_session, owner)  # persist synthetic owner for audit
    before = await ledger(db_session)
    async with client_for(db_session, owner) as client:
        created = await client.post("/api/finance/people", json={"name": "Donor"})
        assert created.status_code == 201, created.text
        p = created.json()
        path = f"/api/finance/transactions/{txn.id}/person-link"
        ctx = await client.get(path)
        assert ctx.status_code == 200, ctx.text
        payload = {"person_id": p["id"], "expected_transaction_snapshot": ctx.json()["snapshot"]}
        linked = await client.put(path, json=payload, headers={"Idempotency-Key": "link"})
        assert linked.status_code == 200, linked.text
        assert (
            await client.put(path, json=payload, headers={"Idempotency-Key": "link"})
        ).json() == linked.json()
        summary = await client.get(f"/api/finance/people/{p['id']}/summary")
        assert summary.json()["received_gifts_pln"] == 10000
        history = await client.get(f"/api/finance/people/{p['id']}/gifts")
        assert history.json()["total"] == 1
        assert history.json()["items"][0]["id"] == str(txn.id)
        unlinked = await client.request(
            "DELETE",
            path,
            json={"expected_transaction_snapshot": linked.json()["snapshot"]},
            headers={"Idempotency-Key": "unlink"},
        )
        assert unlinked.status_code == 200 and unlinked.json()["person"] is None
    assert await ledger(db_session) == before


async def test_person_api_scope_validation_and_protected_history(db_session):
    owner, txn, _, _ = await gift(db_session)
    p = await person(db_session, owner)
    async with client_for(db_session, uuid.uuid4()) as client:
        for endpoint in [
            f"people/{p.id}",
            f"people/{p.id}/summary",
            f"people/{p.id}/gifts",
            f"transactions/{txn.id}/person-link",
        ]:
            assert (await client.get("/api/finance/" + endpoint)).status_code == 404
    async with client_for(db_session, owner) as client:
        assert (await client.get("/api/finance/people?limit=101")).status_code == 422
        assert (await client.get("/api/finance/people?offset=-1")).status_code == 422
        assert (
            await client.post("/api/finance/people", json={"name": "x", "user_id": str(owner)})
        ).status_code == 422
        assert (
            await client.patch(
                f"/api/finance/people/{p.id}", json={"expected_version": 99, "name": "Other"}
            )
        ).status_code == 409


async def test_person_routes_require_authentication_and_csrf(db_session):
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/finance/people")).status_code == 401
        response = await client.post(
            "/api/finance/people", json={"name": "X"}, cookies={"advisor_session": "invalid"}
        )
        assert response.status_code in {401, 403}
