"""Two explicit dates must not duplicate money or rewrite legacy evidence."""

from datetime import date

import pytest
from sqlalchemy import func, select

from app.audit.models import AuditEvent
from app.finance import service
from app.finance.actual_history import transaction_fingerprint
from app.finance.models import ActualImportMapping, FinancialTransaction
from app.finance.schemas import TransactionCreate, TransactionResponse
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bill_guards import allocated
from tests.test_finance.test_bill_payments import create_owner
from tests.test_finance.test_transaction_search import seed

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
PURCHASE = date(2026, 1, 30)
BOOKING = date(2026, 2, 2)


async def explicit(db, owner):
    old, account, category = await seed(db, owner, day=BOOKING, amount=10000)
    payload = TransactionResponse.model_validate(old).model_dump(mode="json")
    postings = [
        {
            k: p[k]
            for k in (
                "account_id",
                "category_id",
                "source_amount",
                "source_currency",
                "base_amount_pln",
                "fx_rate",
                "fx_rate_source",
                "direction",
            )
        }
        for p in payload["postings"]
    ]
    return (
        await service.create_transaction(
            db,
            owner,
            TransactionCreate(
                type="expense",
                description="Synthetic receipt",
                purchase_date=PURCHASE,
                booking_date=BOOKING,
                postings=postings,
            ),
        ),
        old,
        account,
        category,
    )


async def patch_dates(client, txn, **overrides):
    current = (await client.get(f"/api/finance/transactions/{txn.id}")).json()
    payload = {
        "purchase_date": PURCHASE.isoformat(),
        "booking_date": BOOKING.isoformat(),
        "expected_version": (current.get("date_metadata") or {}).get("version", 0),
        "expected_updated_at": current["updated_at"],
    }
    payload.update(overrides)
    return await client.patch(f"/api/finance/transactions/{txn.id}/dates", json=payload)


async def test_explicit_create_preserves_one_payment_and_manual_date_provenance(db_session):
    owner = await create_owner(db_session)
    txn, legacy, account, _ = await explicit(db_session, owner)
    assert txn.date == BOOKING
    payload = TransactionResponse.model_validate(txn).model_dump(mode="json")
    meta = payload.get("date_metadata")
    assert meta is not None, "New explicit dates must not be silently ignored"
    assert (
        meta["purchase_date"] == PURCHASE.isoformat()
        and meta["booking_date"] == BOOKING.isoformat()
    )
    assert meta["purchase_date_source"] == meta["booking_date_source"] == "manual"
    assert meta["version"] == 1
    assert TransactionResponse.model_validate(legacy).model_dump().get("date_metadata") is None
    assert (
        len(txn.postings) == 2
        and sum(
            p.base_amount_pln if p.direction == "debit" else -p.base_amount_pln
            for p in txn.postings
        )
        == 0
    )
    assert (await service.get_account(db_session, owner, account.id)).balance_pln == -20000


async def test_manual_annotation_keeps_legacy_fingerprint_when_booking_unchanged(db_session):
    owner = await create_owner(db_session)
    txn, _, _ = await seed(db_session, owner, day=BOOKING)
    before = transaction_fingerprint(txn)
    async with client_for(db_session, owner) as client:
        response = await patch_dates(client, txn)
    assert response.status_code == 200, response.text
    assert response.json()["date_metadata"]["purchase_date"] == PURCHASE.isoformat()
    assert transaction_fingerprint(txn) == before
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "set_transaction_dates")
        )
        == 1
    )


async def test_owned_date_correction_rejects_stale_version_and_preserves_posting_ids(db_session):
    owner = await create_owner(db_session)
    txn, _, _ = await seed(db_session, owner, day=BOOKING)
    posting_ids = [p.id for p in txn.postings]
    async with client_for(db_session, owner) as client:
        response = await patch_dates(client, txn)
        assert response.status_code == 200, response.text
        stale = await patch_dates(client, txn, expected_version=0, purchase_date="2026-01-29")
        assert stale.status_code == 409
        noop = await patch_dates(client, txn)
        assert noop.status_code == 200 and noop.json()["date_metadata"]["version"] == 1
    assert [p.id for p in txn.postings] == posting_ids
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "set_transaction_dates")
        )
        == 1
    )


async def test_foreign_date_correction_returns404_without_writing(db_session):
    owner = await create_owner(db_session)
    other = await create_owner(db_session)
    txn, _, _ = await seed(db_session, owner, day=BOOKING)
    async with client_for(db_session, other) as client:
        response = await client.patch(
            f"/api/finance/transactions/{txn.id}/dates",
            json={
                "purchase_date": PURCHASE.isoformat(),
                "booking_date": BOOKING.isoformat(),
                "expected_version": 0,
                "expected_updated_at": txn.updated_at.isoformat(),
            },
        )
    assert response.status_code == 404
    assert await db_session.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize("mapped", [False, True])
async def test_imported_actual_dates_are_not_silently_reclassified(db_session, mapped):
    owner = await create_owner(db_session)
    txn, _, _ = await seed(db_session, owner, day=BOOKING)
    if mapped:
        db_session.add(
            ActualImportMapping(
                user_id=owner, entity_type="transaction", actual_id="synthetic", entity_id=txn.id
            )
        )
    else:
        txn.source = "actual"
    await db_session.flush()
    await db_session.refresh(txn, attribute_names=["updated_at"])
    before = transaction_fingerprint(txn)
    async with client_for(db_session, owner) as client:
        response = await patch_dates(client, txn)
    assert response.status_code == 409, response.text
    assert transaction_fingerprint(txn) == before


async def test_allocated_payment_dates_remain_protected(db_session):
    owner, _, txn_id, _, _, _ = await allocated(db_session)
    txn = await service.get_transaction(db_session, owner, txn_id)
    async with client_for(db_session, owner) as client:
        response = await patch_dates(client, txn)
    assert response.status_code == 409, response.text


async def test_stale_transaction_snapshot_requires_new_decision(db_session):
    owner = await create_owner(db_session)
    txn, _, _ = await seed(db_session, owner, day=BOOKING)
    async with client_for(db_session, owner) as client:
        response = await patch_dates(client, txn, expected_updated_at="2020-01-01T00:00:00Z")
    assert response.status_code == 409, response.text


async def test_generic_legacy_patch_cannot_desynchronize_explicit_booking_date(db_session):
    owner = await create_owner(db_session)
    txn, _, _, _ = await explicit(db_session, owner)
    async with client_for(db_session, owner) as client:
        response = await client.patch(
            f"/api/finance/transactions/{txn.id}", json={"transaction_date": "2026-02-03"}
        )
    assert response.status_code == 409, response.text
    assert txn.date == BOOKING


async def test_deleting_authorized_manual_transaction_leaves_no_date_orphan(db_session):
    owner = await create_owner(db_session)
    txn, _, _, _ = await explicit(db_session, owner)
    assert TransactionResponse.model_validate(txn).model_dump().get("date_metadata") is not None
    async with client_for(db_session, owner) as client:
        deleted = await client.delete(f"/api/finance/transactions/{txn.id}")
    assert deleted.status_code == 204
    from app.finance.models import TransactionDateMetadata

    assert await db_session.scalar(select(func.count()).select_from(TransactionDateMetadata)) == 0
    assert await db_session.get(FinancialTransaction, txn.id) is None


async def test_linked_loan_date_change_rejected_and_description_remains_editable(db_session):
    from app.finance.models import LoanAgreement, LoanInstallment, LoanPaymentLink

    owner = await create_owner(db_session)
    txn, account, _ = await seed(db_session, owner, day=BOOKING)
    _, other, _ = await seed(db_session, owner, day=BOOKING)
    loan = LoanAgreement(
        user_id=owner, name="Synthetic loan", account_id=account.id, payment_account_id=other.id
    )
    db_session.add(loan)
    await db_session.flush()
    installment = LoanInstallment(
        user_id=owner,
        loan_id=loan.id,
        number=1,
        due_date=BOOKING,
        principal_pln=10000,
        interest_pln=0,
        fees_pln=0,
    )
    db_session.add(installment)
    await db_session.flush()
    db_session.add(
        LoanPaymentLink(user_id=owner, installment_id=installment.id, transaction_id=txn.id)
    )
    await db_session.flush()
    async with client_for(db_session, owner) as client:
        response = await patch_dates(client, txn)
        assert response.status_code == 409
        narrative = await client.patch(
            f"/api/finance/transactions/{txn.id}", json={"description": "Narrative only"}
        )
        assert narrative.status_code == 200
    assert txn.date == BOOKING


@pytest.mark.parametrize(
    "extra",
    [
        {"purchase_date_source": "bank"},
        {"source": "bank"},
        {"booking_date": None},
        {"expected_version": True},
    ],
)
async def test_date_endpoint_rejects_spoofed_provenance_and_malformed_input(db_session, extra):
    owner = await create_owner(db_session)
    txn, _, _ = await seed(db_session, owner, day=BOOKING)
    async with client_for(db_session, owner) as client:
        response = await patch_dates(client, txn, **extra)
    assert response.status_code == 422
    assert await db_session.scalar(select(func.count()).select_from(AuditEvent)) == 0
