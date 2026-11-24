"""Contract-only checks for the atomic transaction editor request shape."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.finance.models import Posting
from app.finance.schemas import TransactionEditorUpdate
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_categorization import setup


def test_editor_update_requires_timezone_aware_optimistic_lock() -> None:
    """A naive timestamp must not accidentally compare in server local time."""
    with pytest.raises(ValidationError, match="Expected timestamp requires a timezone"):
        TransactionEditorUpdate.model_validate(
            {
                "expected_updated_at": datetime(2026, 11, 24, 12, 0),
                "ledger": {
                    "kind": "transaction",
                    "data": {
                        "transaction_date": "2026-11-24",
                        "description": "Lunch",
                        "type": "expense",
                        "postings": [
                            {
                                "account_id": str(uuid4()),
                                "source_amount": 100,
                                "base_amount_pln": 100,
                                "direction": "debit",
                            },
                            {
                                "category_id": str(uuid4()),
                                "source_amount": 100,
                                "base_amount_pln": 100,
                                "direction": "credit",
                            },
                        ],
                    },
                },
            }
        )


def test_editor_update_accepts_transaction_replacement_payload() -> None:
    request = TransactionEditorUpdate.model_validate(
        {
            "expected_updated_at": datetime(2026, 11, 24, 12, 0, tzinfo=UTC),
            "ledger": {
                "kind": "transaction",
                "data": {
                    "transaction_date": "2026-11-24",
                    "description": "Lunch",
                    "type": "expense",
                    "postings": [
                        {
                            "account_id": str(uuid4()),
                            "source_amount": 100,
                            "base_amount_pln": 100,
                            "direction": "debit",
                        },
                        {
                            "category_id": str(uuid4()),
                            "source_amount": 100,
                            "base_amount_pln": 100,
                            "direction": "credit",
                        },
                    ],
                },
            },
        }
    )

    assert request.ledger is not None
    assert request.ledger.kind == "transaction"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_editor_updates_canonical_manual_ledger_in_place(db_session) -> None:
    owner, txn, _, _, _ = await setup(db_session)
    posting_ids = {posting.id for posting in txn.postings}
    async with client_for(db_session, owner) as client:
        opened = await client.get(f"/api/finance/transactions/{txn.id}/editor")
        assert opened.status_code == 200, opened.text
        editor = opened.json()
        assert editor["ledger_editable"] is True
        transaction = editor["transaction"]
        replacement = {
            "transaction_date": transaction["transaction_date"],
            "description": "Corrected title",
            "type": transaction["type"],
            "is_pending": transaction["is_pending"],
            "source": "manual",
            "postings": [
                {
                    key: posting[key]
                    for key in (
                        "account_id",
                        "category_id",
                        "source_amount",
                        "source_currency",
                        "base_amount_pln",
                        "fx_rate",
                        "fx_rate_source",
                        "direction",
                        "is_budget_impact",
                    )
                }
                for posting in transaction["postings"]
            ],
        }
        saved = await client.put(
            f"/api/finance/transactions/{txn.id}/editor",
            json={
                "expected_updated_at": transaction["updated_at"],
                "ledger": {"kind": "transaction", "data": replacement},
            },
        )
    assert saved.status_code == 200, saved.text
    assert saved.json()["transaction"]["id"] == str(txn.id)
    assert {posting.id for posting in txn.postings} == posting_ids
    assert saved.json()["transaction"]["description"] == "Corrected title"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_editor_locks_split_layout_without_erasing_annotation_boundary(db_session) -> None:
    owner, txn, _, _, _ = await setup(db_session)
    first = txn.postings[0]
    db_session.add(
        Posting(
            transaction_id=txn.id,
            category_id=txn.postings[1].category_id,
            source_amount=1,
            source_currency=first.source_currency,
            base_amount_pln=1,
            fx_rate=first.fx_rate,
            fx_rate_source=first.fx_rate_source,
            direction=txn.postings[1].direction,
            is_budget_impact=True,
        )
    )
    first.source_amount -= 1
    first.base_amount_pln -= 1
    await db_session.commit()
    async with client_for(db_session, owner) as client:
        opened = await client.get(f"/api/finance/transactions/{txn.id}/editor")
    assert opened.status_code == 200, opened.text
    assert opened.json()["ledger_editable"] is False
    assert "Podział" in opened.json()["ledger_lock_reason"]
