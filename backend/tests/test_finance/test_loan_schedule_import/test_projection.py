from datetime import date

import pytest
from sqlalchemy import select

from app.finance import loans
from app.finance.loan_schemas import LoanInstallmentCreate, LoanInstallmentUpdate
from app.finance.models import LoanInstallment, LoanPaymentLink
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_loan_schedule_import.factories import (
    financial_history_snapshot,
    legacy_loan,
    payment_transfer,
    schedule_version,
)

pytestmark = pytest.mark.integration


async def test_detail_and_list_exclude_superseded_future_but_preserve_history(db_session, owner):
    loan, old, receipt = await legacy_loan(db_session, owner.id)
    old_id = old.id
    historical = await loans.create_loan_installment(
        db_session,
        owner.id,
        loan.id,
        LoanInstallmentCreate(
            number=2, due_date=date(2020, 1, 1), principal_pln=2000, interest_pln=100, fees_pln=0
        ),
    )
    future = await loans.create_loan_installment(
        db_session,
        owner.id,
        loan.id,
        LoanInstallmentCreate(
            number=3, due_date=date(2027, 1, 1), principal_pln=3000, interest_pln=200, fees_pln=0
        ),
    )
    revision = await schedule_version(db_session, owner.id, loan, receipt)
    old.superseded_by_revision_id = revision.id
    await db_session.flush()
    before = await financial_history_snapshot(db_session)
    detail = await loans.get_loan(db_session, owner.id, loan.id)
    assert detail is not None
    assert {i.id for i in detail.installments} == {historical.id, future.id}
    assert detail.planned_principal_pln == 5000 and detail.planned_interest_pln == 300
    assert detail.active_schedule_revision_id == revision.id
    listed = await loans.get_loans(db_session, owner.id)
    assert listed[0].total_planned_pln == 5300
    assert await db_session.get(LoanInstallment, old_id) is not None
    assert await financial_history_snapshot(db_session) == before


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_bank_managed_plan_rejects_manual_mutation_with_http409(db_session, owner, operation):
    loan, item, receipt = await legacy_loan(db_session, owner.id)
    await schedule_version(db_session, owner.id, loan, receipt, bank=True)
    before = await financial_history_snapshot(db_session)
    async with client_for(db_session, owner.id) as client:
        url = f"/api/finance/loans/{loan.id}/installments"
        if operation == "create":
            response = await client.post(
                url,
                json={
                    "number": 2,
                    "due_date": "2027-01-01",
                    "principal_pln": 100,
                    "interest_pln": 0,
                    "fees_pln": 0,
                },
            )
        elif operation == "update":
            response = await client.patch(url + f"/{item.id}", json={"interest_pln": 999})
        else:
            response = await client.delete(url + f"/{item.id}")
    assert response.status_code == 409, response.text
    assert "import" in response.json()["detail"].lower()
    assert await financial_history_snapshot(db_session) == before
    await db_session.refresh(item)
    assert item.interest_pln == 500


async def test_superseded_row_rejects_new_links_and_candidates_with_http409(db_session, owner):
    loan, item, receipt = await legacy_loan(db_session, owner.id)
    transaction = await payment_transfer(db_session, owner.id, loan)
    revision = await schedule_version(db_session, owner.id, loan, receipt)
    item.superseded_by_revision_id = revision.id
    await db_session.flush()
    before = await financial_history_snapshot(db_session)
    async with client_for(db_session, owner.id) as client:
        root = f"/api/finance/loans/{loan.id}/installments/{item.id}"
        assert (await client.get(root + "/payment-candidates")).status_code == 409
        assert (
            await client.post(root + "/payments", json={"transaction_id": str(transaction.id)})
        ).status_code == 409
    assert await financial_history_snapshot(db_session) == before


async def test_retained_historical_link_unlink_remains_addressable_after_bank_version(
    db_session, owner
):
    loan, item, receipt = await legacy_loan(db_session, owner.id)
    item.due_date = date(2020, 1, 1)
    await db_session.flush()
    transaction = await payment_transfer(db_session, owner.id, loan)
    await loans.link_loan_payment(db_session, owner.id, loan.id, item.id, transaction.id)
    link = await db_session.scalar(
        select(LoanPaymentLink).where(LoanPaymentLink.installment_id == item.id)
    )
    link_id = link.id
    await schedule_version(db_session, owner.id, loan, receipt, bank=True)
    assert await loans.unlink_loan_payment(db_session, owner.id, loan.id, link_id)
    detail = await loans.get_loan(db_session, owner.id, loan.id)
    assert detail.installments[0].id == item.id and detail.installments[0].paid_pln == 0
    assert (
        await loans.link_loan_payment(db_session, owner.id, loan.id, item.id, transaction.id)
        is not None
    )


async def test_fingerprint_changes_for_fields_payments_and_unlinks_not_just_agreement(
    db_session, owner, other_owner
):
    from app.finance.loan_schedule_diff import load_schedule_state

    loan, item, _ = await legacy_loan(db_session, owner.id)
    first = await load_schedule_state(db_session, owner.id, loan.id, lock=False)
    await loans.update_loan_installment(
        db_session, owner.id, loan.id, item.id, LoanInstallmentUpdate(interest_pln=501)
    )
    second = await load_schedule_state(db_session, owner.id, loan.id, lock=False)
    assert first.fingerprint != second.fingerprint
    transaction = await payment_transfer(db_session, owner.id, loan)
    await loans.link_loan_payment(db_session, owner.id, loan.id, item.id, transaction.id)
    third = await load_schedule_state(db_session, owner.id, loan.id, lock=False)
    assert second.fingerprint != third.fingerprint
    link = await db_session.scalar(
        select(LoanPaymentLink).where(LoanPaymentLink.installment_id == item.id)
    )
    await loans.unlink_loan_payment(db_session, owner.id, loan.id, link.id)
    fourth = await load_schedule_state(db_session, owner.id, loan.id, lock=False)
    assert third.fingerprint != fourth.fingerprint
    assert first.installments[0].interest_pln == 500  # immutable preview input
    assert await load_schedule_state(db_session, other_owner.id, loan.id, lock=False) is None
