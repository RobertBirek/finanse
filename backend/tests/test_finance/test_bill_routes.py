import uuid
from datetime import date

import pytest

from app.documents.models import Document
from app.finance.models import FinancialDocument
from app.identity.models import User
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bill_payments import create_owner, setup_bill

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_prepare_route_is_explicit_and_replays(db_session) -> None:
    user = User(email=f"{uuid.uuid4()}@example.test", password_hash="x", display_name="Owner")
    db_session.add(user)
    await db_session.flush()
    document = Document(
        user_id=user.id,
        filename="route.pdf",
        original_name="route.pdf",
        mime_type="application/pdf",
        sha256_hash=uuid.uuid4().hex * 2,
        size_bytes=1,
        storage_path="test/route.pdf",
    )
    db_session.add(document)
    await db_session.flush()
    async with client_for(db_session, user.id) as client:
        created = await client.post(
            f"/api/finance/bills/prepare/{document.id}", headers={"Idempotency-Key": "prepare"}
        )
        replay = await client.post(
            f"/api/finance/bills/prepare/{document.id}", headers={"Idempotency-Key": "prepare"}
        )
    assert created.status_code == 201
    assert replay.json() == created.json()


async def test_list_route_applies_due_dates_and_text_before_counting_pages(db_session) -> None:
    """Removing route query passthrough must change this filtered page and its total."""
    owner = await create_owner(db_session)
    matching = await setup_bill(db_session, owner)
    matching.supplier_name, matching.due_date = "Needle supplier", date(2026, 11, 10)
    other = await setup_bill(db_session, owner)
    other.supplier_name, other.due_date = "Other supplier", date(2026, 12, 10)
    await db_session.flush()

    async with client_for(db_session, owner) as client:
        response = await client.get(
            "/api/finance/bills",
            params={
                "due_from": "2026-11-01",
                "due_to": "2026-11-30",
                "query": "Needle",
                "limit": 1,
                "offset": 0,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["id"] for item in payload["items"]] == [str(matching.id)]


async def test_lifecycle_route_requires_server_side_forecast_confirmation(db_session) -> None:
    """The lifecycle API, not only its modal, must protect a remaining payable obligation."""
    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    bill.declaration = "payable"
    bill_id, version = bill.id, bill.version
    await db_session.commit()
    async with client_for(db_session, owner) as client:
        rejected = await client.post(
            f"/api/finance/bills/{bill_id}/lifecycle",
            json={"expected_version": version, "lifecycle": "archived"},
            headers={"Idempotency-Key": "unconfirmed"},
        )
        confirmed = await client.post(
            f"/api/finance/bills/{bill_id}/lifecycle",
            json={
                "expected_version": version,
                "lifecycle": "archived",
                "confirm_forecast_effect": True,
            },
            headers={"Idempotency-Key": "confirmed"},
        )
        replay = await client.post(
            f"/api/finance/bills/{bill_id}/lifecycle",
            json={
                "expected_version": version,
                "lifecycle": "archived",
                "confirm_forecast_effect": True,
            },
            headers={"Idempotency-Key": "confirmed"},
        )
        stale = await client.post(
            f"/api/finance/bills/{bill_id}/lifecycle",
            json={
                "expected_version": version,
                "lifecycle": "active",
            },
            headers={"Idempotency-Key": "stale"},
        )
        reopened = await client.post(
            f"/api/finance/bills/{bill_id}/lifecycle",
            json={"expected_version": version + 1, "lifecycle": "active"},
            headers={"Idempotency-Key": "reopen"},
        )
    assert rejected.status_code == 422
    assert confirmed.status_code == 200
    assert replay.json() == confirmed.json()
    assert stale.status_code == 409
    assert reopened.status_code == 200


async def test_approval_returns_owner_duplicate_candidates_for_submitted_fields(db_session) -> None:
    owner = await create_owner(db_session)
    other = await create_owner(db_session)
    existing = await setup_bill(db_session, owner)
    second = await setup_bill(db_session, owner)
    foreign = await setup_bill(db_session, other)
    existing.issue_date = second.issue_date = foreign.issue_date = date(2026, 10, 28)
    existing.number, second.number, foreign.number = "FV-1", "FV-2", "FV-3"
    draft = FinancialDocument(user_id=owner)
    db_session.add(draft)
    await db_session.flush()
    draft_id = str(draft.id)
    candidate_ids = {str(existing.id): "FV-1", str(second.id): "FV-2"}
    await db_session.commit()
    payload = {
        "version": 1,
        "kind": "invoice",
        "supplier_name": "Supplier",
        "issue_date": "2026-10-28",
        "description": "Manually entered PDF values",
        "total_minor": 10_000,
        "currency": "PLN",
    }
    async with client_for(db_session, owner) as client:
        duplicate = await client.post(
            f"/api/finance/bills/{draft_id}/approve",
            json=payload,
            headers={"Idempotency-Key": "check-duplicate"},
        )
        unchanged = await client.get(f"/api/finance/bills/{draft_id}")
        approved = await client.post(
            f"/api/finance/bills/{draft_id}/approve",
            json={**payload, "duplicate_decision": "separate"},
            headers={"Idempotency-Key": "approve-separately"},
        )
    assert duplicate.status_code == 422
    assert duplicate.json()["detail"] == "duplicate_decision_required"
    candidates = duplicate.json()["duplicate_candidates"]
    assert {item["id"]: item["number"] for item in candidates} == candidate_ids
    for candidate in candidates:
        assert candidate == {
            "id": candidate["id"],
            "reasons": ["supplier_amount_currency"],
            "supplier_name": "Supplier",
            "number": candidate_ids[candidate["id"]],
            "issue_date": "2026-10-28",
            "total_minor": 10_000,
            "currency": "PLN",
        }
    assert unchanged.json()["review"] == "draft"
    assert unchanged.json()["version"] == 1
    assert approved.status_code == 200
    assert approved.json()["review"] == "approved"
    assert approved.json()["version"] == 2
