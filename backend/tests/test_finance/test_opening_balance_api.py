"""The dedicated BO endpoint cannot be replaced by a general account patch."""

import uuid

import pytest

from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_opening_balances import owner_record

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_account_opening_api_scope_validation_and_replay(db_session):
    owner = await owner_record(db_session)
    async with client_for(db_session, owner) as client:
        created = await client.post(
            "/api/finance/accounts",
            json={
                "name": "Opening bank",
                "type": "checking",
                "opening_balance": {"amount_minor": -12345, "date": "2026-11-16"},
            },
        )
        assert created.status_code == 201, created.text
        account = created.json()
        assert account["balance_source"] == -12345
        assert account["opening_balance"]["amount_minor"] == -12345
        path = f"/api/finance/accounts/{account['id']}/opening-balance"
        payload = {"amount_minor": 25000, "date": "2026-11-15", "expected_version": 1}
        response = await client.put(path, json=payload, headers={"Idempotency-Key": "bo"})
        assert response.status_code == 200, response.text
        assert response.json()["amount_minor"] == 25000
        assert (
            await client.put(path, json=payload, headers={"Idempotency-Key": "bo"})
        ).json() == response.json()
        assert (
            await client.put(path, json=payload, headers={"Idempotency-Key": "stale"})
        ).status_code == 409
        assert (await client.put(path, json=payload)).status_code == 422
        assert (
            await client.patch(
                f"/api/finance/accounts/{account['id']}",
                json={"opening_balance": {"amount_minor": 5}},
            )
        ).status_code == 422
    async with client_for(db_session, uuid.uuid4()) as client:
        assert (
            await client.put(path, json=payload, headers={"Idempotency-Key": "bo"})
        ).status_code == 404
