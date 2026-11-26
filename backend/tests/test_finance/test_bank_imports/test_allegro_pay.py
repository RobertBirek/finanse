import uuid

import pytest

from tests.test_finance.test_account_currency import client_for


@pytest.mark.integration
async def test_allegro_pay_purchase_and_split_payment_are_owned_and_retry_safe(
    db_session, owner, other_owner
):
    async with client_for(db_session, owner.id) as client:
        debt = await client.post(
            "/api/finance/accounts", json={"name": "Allegro", "type": "credit"}
        )
        payer = await client.post(
            "/api/finance/accounts", json={"name": "Bank", "type": "checking"}
        )
        category = await client.post(
            "/api/finance/categories", json={"name": "Zakupy", "type": "expense"}
        )
        assert debt.status_code == payer.status_code == category.status_code == 201
        account_id = debt.json()["id"]
        configured = await client.put(
            "/api/finance/allegro-pay", json={"account_id": account_id, "limit_pln": 100000}
        )
        assert configured.status_code == 200
        profile_id = configured.json()["id"]
        request = {
            "request_id": str(uuid.uuid4()),
            "name": "Syntetyczny zakup",
            "purchase_date": "2026-01-01",
            "principal_pln": 20000,
            "category_id": category.json()["id"],
            "installments": [
                {
                    "due_date": "2026-02-01",
                    "principal_pln": 10000,
                    "interest_pln": 0,
                    "fees_pln": 0,
                },
                {
                    "due_date": "2026-03-01",
                    "principal_pln": 10000,
                    "interest_pln": 0,
                    "fees_pln": 0,
                },
            ],
        }
        created = await client.post(
            f"/api/finance/allegro-pay/{profile_id}/purchases", json=request
        )
        assert created.status_code == 200
        assert (
            await client.post(f"/api/finance/allegro-pay/{profile_id}/purchases", json=request)
        ).json() == created.json()
        changed = request | {"name": "Inny"}
        assert (
            await client.post(f"/api/finance/allegro-pay/{profile_id}/purchases", json=changed)
        ).status_code == 422
        overview = (await client.get("/api/finance/allegro-pay")).json()[0]
        assert overview["ledger_balance_pln"] == -20000
        assert overview["available_pln"] == 80000
        assert overview["scheduled_remaining_pln"] == 20000
        installments = overview["purchases"][0]["installments"]
        transfer = await client.post(
            "/api/finance/transactions",
            json={
                "description": "Syntetyczna spłata",
                "type": "transfer",
                "transaction_date": "2026-01-15",
                "postings": [
                    {
                        "account_id": payer.json()["id"],
                        "source_amount": 15000,
                        "base_amount_pln": 15000,
                        "direction": "debit",
                    },
                    {
                        "account_id": account_id,
                        "source_amount": 15000,
                        "base_amount_pln": 15000,
                        "direction": "credit",
                    },
                ],
            },
        )
        assert transfer.status_code == 201
        payment = {
            "transaction_id": transfer.json()["id"],
            "allocations": [
                {"installment_id": installments[0]["id"], "amount_pln": 10000},
                {"installment_id": installments[1]["id"], "amount_pln": 5000},
            ],
        }
        endpoint = f"/api/finance/allegro-pay/{profile_id}/payments"
        assert (await client.post(endpoint, json=payment)).status_code == 200
        assert (await client.post(endpoint, json=payment)).status_code == 200
        result = (await client.get("/api/finance/allegro-pay")).json()[0]
        assert result["scheduled_remaining_pln"] == 5000
        assert result["ledger_balance_pln"] == -5000
        assert (
            await client.delete(f"/api/finance/transactions/{transfer.json()['id']}")
        ).status_code in (409, 422)
    async with client_for(db_session, other_owner.id) as client:
        assert (await client.get("/api/finance/allegro-pay")).json() == []
        assert (await client.post(endpoint, json=payment)).status_code == 404


def test_schedule_validation_rejects_wrong_principal():
    from pydantic import ValidationError

    from app.finance.allegro_pay_schemas import PurchaseInput

    with pytest.raises(ValidationError):
        PurchaseInput.model_validate(
            {
                "request_id": str(uuid.uuid4()),
                "name": "Zakup",
                "purchase_date": "2026-01-01",
                "principal_pln": 10000,
                "transaction_id": str(uuid.uuid4()),
                "installments": [
                    {
                        "due_date": "2026-02-01",
                        "principal_pln": 9999,
                        "interest_pln": 0,
                        "fees_pln": 0,
                    }
                ],
            }
        )
