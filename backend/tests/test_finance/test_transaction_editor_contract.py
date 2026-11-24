"""Contract-only checks for the atomic transaction editor request shape."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.finance.models import FinancialTransaction, Posting
from app.finance.schemas import TransactionEditorUpdate
from app.finance.transaction_editor import _is_canonical_manual_fx
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bill_payments import create_owner
from tests.test_finance.test_categorization import setup
from tests.test_finance.test_transaction_dates import explicit


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


def test_editor_update_accepts_nonnegative_date_version() -> None:
    request = TransactionEditorUpdate.model_validate(
        {
            "expected_updated_at": datetime(2026, 11, 24, 12, 0, tzinfo=UTC),
            "expected_date_version": 1,
            "annotations": {
                "display_description": None,
                "note": None,
                "tags": [],
                "project_id": None,
                "expected_version": 0,
                "expected_context_snapshot": "0" * 64,
            },
        }
    )

    assert request.expected_date_version == 1


def test_manual_fx_shape_requires_same_currency_and_manual_rate_provenance() -> None:
    txn = FinancialTransaction(source="manual", type="expense")
    txn.postings = [
        Posting(
            account_id=uuid4(),
            source_amount=1234,
            source_currency="EUR",
            base_amount_pln=5244,
            fx_rate=4.25,
            fx_rate_source="manual",
            direction="debit",
            is_budget_impact=True,
        ),
        Posting(
            category_id=uuid4(),
            source_amount=1234,
            source_currency="EUR",
            base_amount_pln=5244,
            fx_rate=4.25,
            fx_rate_source="manual",
            direction="credit",
            is_budget_impact=True,
        ),
    ]

    assert _is_canonical_manual_fx(txn) is True
    txn.postings[1].fx_rate_source = "nbp"
    assert _is_canonical_manual_fx(txn) is False


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
async def test_editor_updates_manual_expense_dates_with_date_version(db_session) -> None:
    owner = await create_owner(db_session)
    txn, _, _, _ = await explicit(db_session, owner)
    async with client_for(db_session, owner) as client:
        opened = await client.get(f"/api/finance/transactions/{txn.id}/editor")
        assert opened.status_code == 200, opened.text
        editor = opened.json()
        transaction = editor["transaction"]
        assert editor["ledger_editable"] is True
        assert transaction["date_metadata"]["version"] == 1
        replacement = {
            "purchase_date": "2026-01-31",
            "booking_date": "2026-02-03",
            "description": transaction["description"],
            "type": "expense",
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
                "expected_date_version": transaction["date_metadata"]["version"],
                "ledger": {"kind": "transaction", "data": replacement},
            },
        )
    assert saved.status_code == 200, saved.text
    assert saved.json()["transaction"]["id"] == str(txn.id)
    assert saved.json()["transaction"]["transaction_date"] == "2026-02-03"
    assert saved.json()["transaction"]["date_metadata"] == {
        "purchase_date": "2026-01-31",
        "booking_date": "2026-02-03",
        "purchase_date_source": "manual",
        "booking_date_source": "manual",
        "version": 2,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_editor_rolls_back_annotation_when_manual_date_version_is_stale(db_session) -> None:
    owner = await create_owner(db_session)
    txn, _, _, _ = await explicit(db_session, owner)
    # The HTTP test client shares this session. Commit the preexisting
    # transaction so the endpoint rollback only undoes the attempted edit.
    await db_session.commit()
    # Rollback expires ORM objects; the follow-up HTTP request must not
    # trigger an implicit async reload when interpolating the URL.
    editor_url = f"/api/finance/transactions/{txn.id}/editor"
    async with client_for(db_session, owner) as client:
        opened = await client.get(editor_url)
        assert opened.status_code == 200, opened.text
        transaction = opened.json()["transaction"]
        annotation = transaction["annotations"]
        rejected = await client.put(
            editor_url,
            headers={"Idempotency-Key": "editor-date-rollback"},
            json={
                "expected_updated_at": transaction["updated_at"],
                "expected_date_version": transaction["date_metadata"]["version"] + 1,
                "annotations": {
                    "display_description": annotation["display_description"],
                    "note": "must roll back",
                    "tags": [tag["name"] for tag in annotation["tags"]],
                    "project_id": annotation["project_id"],
                    "expected_version": annotation["version"],
                    "expected_context_snapshot": annotation["context_snapshot"],
                },
                "ledger": {
                    "kind": "transaction",
                    "data": {
                        "purchase_date": transaction["date_metadata"]["purchase_date"],
                        "booking_date": transaction["date_metadata"]["booking_date"],
                        "description": transaction["description"],
                        "type": "expense",
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
                    },
                },
            },
        )
        assert rejected.status_code == 409, rejected.text
        after = await client.get(editor_url)
    assert after.status_code == 200, after.text
    assert after.json()["transaction"] == transaction


@pytest.mark.integration
@pytest.mark.asyncio
async def test_editor_locks_split_layout_without_erasing_annotation_boundary(db_session) -> None:
    owner, txn, _, _, home = await setup(db_session)
    category_posting = next(posting for posting in txn.postings if posting.category_id)
    db_session.add(
        Posting(
            transaction_id=txn.id,
            category_id=home.id,
            source_amount=1,
            source_currency=category_posting.source_currency,
            base_amount_pln=1,
            fx_rate=category_posting.fx_rate,
            fx_rate_source=category_posting.fx_rate_source,
            direction=category_posting.direction,
            is_budget_impact=category_posting.is_budget_impact,
        )
    )
    category_posting.source_amount -= 1
    category_posting.base_amount_pln -= 1
    await db_session.commit()
    # The test HTTP client reuses this session; load the persisted third leg.
    await db_session.refresh(txn, ["postings"])
    async with client_for(db_session, owner) as client:
        opened = await client.get(f"/api/finance/transactions/{txn.id}/editor")
    assert opened.status_code == 200, opened.text
    assert len(opened.json()["transaction"]["postings"]) == 3
    assert opened.json()["ledger_editable"] is False
    assert "Podział" in opened.json()["ledger_lock_reason"]
