"""Safety properties of the transaction editor against an isolated test database."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.schemas import AccountCreate
from app.finance.service import create_account
from tests.test_finance.test_account_currency import add_history, client_for
from tests.test_finance.test_bill_payments import create_owner

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_editor_preserves_ledger_on_invalid_edit_and_rejects_other_owner(
    db_session: AsyncSession,
) -> None:
    owner = await create_owner(db_session)
    other = await create_owner(db_session)
    account = await create_account(db_session, owner, AccountCreate(name="Test", type="checking"))
    transaction = await add_history(db_session, owner, account)
    account_id = account.id
    transaction_id = transaction.id
    await db_session.commit()

    async with client_for(db_session, owner) as client:
        initial = await client.get(f"/api/finance/transactions/{transaction_id}/editor")
        assert initial.status_code == 200
        before = initial.json()["transaction"]
        annotations = (await client.get(f"/api/finance/transactions/{transaction_id}/annotations")).json()
        category_id = next(p["category_id"] for p in before["postings"] if p["category_id"])
        payload = {
            "expected_updated_at": before["updated_at"],
            "annotations": {
                "display_description": None,
                "note": "Must be rolled back",
                "tags": [],
                "project_id": None,
                "expected_version": annotations["version"],
                "expected_context_snapshot": annotations["context_snapshot"],
            },
            "ledger": {
                "kind": "transaction",
                "data": {
                    "description": "Rejected imbalance",
                    "type": "expense",
                    "postings": [
                        {"account_id": str(account_id), "source_amount": 200,
                         "base_amount_pln": 200, "direction": "debit"},
                        {"category_id": category_id, "source_amount": 100,
                         "base_amount_pln": 100, "direction": "credit"},
                    ],
                },
            },
        }
        rejected = await client.put(
            f"/api/finance/transactions/{transaction_id}/editor",
            json=payload,
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert rejected.status_code == 422
        assert "Sum of posting" in rejected.json()["detail"]
        after = await client.get(f"/api/finance/transactions/{transaction_id}/editor")
        assert after.status_code == 200
        assert after.json()["transaction"] == before
        after_annotations = await client.get(f"/api/finance/transactions/{transaction_id}/annotations")
        assert after_annotations.json() == annotations

    async with client_for(db_session, other) as client:
        assert (await client.get(f"/api/finance/transactions/{transaction_id}/editor")).status_code == 404
        assert (await client.put(f"/api/finance/transactions/{transaction_id}/editor", json=payload)).status_code == 404


async def test_editor_rejects_stale_version_without_changing_ledger(
    db_session: AsyncSession,
) -> None:
    owner = await create_owner(db_session)
    account = await create_account(db_session, owner, AccountCreate(name="Test", type="checking"))
    transaction = await add_history(db_session, owner, account)
    transaction_id = transaction.id
    await db_session.commit()
    async with client_for(db_session, owner) as client:
        response = await client.get(f"/api/finance/transactions/{transaction_id}/editor")
        before = response.json()["transaction"]
        rejected = await client.put(
            f"/api/finance/transactions/{transaction_id}/editor",
            json={
                "expected_updated_at": "2000-01-01T00:00:00Z",
                "annotations": {
                    "display_description": None,
                    "note": "stale",
                    "tags": [],
                    "project_id": None,
                    "expected_version": 0,
                    "expected_context_snapshot": "0" * 64,
                },
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert rejected.status_code == 409
        after = await client.get(f"/api/finance/transactions/{transaction_id}/editor")
        assert after.json()["transaction"] == before
