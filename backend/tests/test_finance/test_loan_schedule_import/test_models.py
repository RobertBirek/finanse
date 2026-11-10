import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.finance.models import LoanInstallment
from tests.test_finance.test_loan_schedule_import.factories import (
    financial_history_snapshot,
    legacy_loan,
)


@asynccontextmanager
async def integrity_rejection(db) -> AsyncIterator[None]:
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            yield


def test_schedule_target_requires_exactly_one_explicit_target():
    from app.finance.loan_schedule_schemas import ScheduleTarget

    target = uuid.uuid4()
    new = {
        "name": "Synthetic",
        "account_id": str(uuid.uuid4()),
        "payment_account_id": str(uuid.uuid4()),
    }
    assert ScheduleTarget(loan_id=target).loan_id == target
    assert ScheduleTarget(new_loan=new).new_loan is not None
    for fields in [{}, {"loan_id": target, "new_loan": new}]:
        with pytest.raises(ValidationError):
            ScheduleTarget(**fields)


def test_schedule_commands_are_strict_and_have_no_ledger_payload():
    from app.finance.loan_schedule_schemas import (
        ScheduleActivateRequest,
        ScheduleCommitResult,
        SchedulePreviewRequest,
    )

    values = {
        "expected_version": 1,
        "source_id": uuid.uuid4(),
        "target": {"loan_id": uuid.uuid4()},
        "acknowledgements": [],
    }
    assert SchedulePreviewRequest(**values).expected_version == 1
    with pytest.raises(ValidationError):
        SchedulePreviewRequest(**(values | {"expected_version": True}))
    with pytest.raises(ValidationError):
        ScheduleActivateRequest(preview_id=uuid.uuid4(), request_hash="a" * 64, postings=[])
    result = {
        "receipt_id": uuid.uuid4(),
        "batch_id": uuid.uuid4(),
        "request_hash": "a" * 64,
        "loan_id": uuid.uuid4(),
        "revision_id": uuid.uuid4(),
        "reused_ids": [],
        "new_ids": [],
        "superseded_ids": [],
        "ledger_changed": False,
    }
    assert ScheduleCommitResult(**result).ledger_changed is False
    with pytest.raises(ValidationError):
        ScheduleCommitResult(**(result | {"ledger_changed": True}))


@pytest.mark.integration
async def test_additive_defaults_leave_legacy_plan_and_finance_unchanged(db_session, owner):
    from app.finance.loan_schedule_models import LoanScheduleMembership, LoanScheduleRevision
    from app.finance.loan_schedule_projection import active_installment_predicate

    loan, installment, _receipt = await legacy_loan(db_session, owner.id)
    before = await financial_history_snapshot(db_session)
    assert (
        loan.active_schedule_revision_id is None and installment.superseded_by_revision_id is None
    )
    assert await db_session.scalar(select(func.count()).select_from(LoanScheduleRevision)) == 0
    assert await db_session.scalar(select(func.count()).select_from(LoanScheduleMembership)) == 0
    assert (
        await db_session.scalars(select(LoanInstallment).where(active_installment_predicate()))
    ).one().id == installment.id
    assert await financial_history_snapshot(db_session) == before


def revision(model, owner, loan, receipt, **changes):
    return model(
        user_id=owner,
        loan_id=loan,
        receipt_id=receipt,
        ordinal=1,
        kind="manual_baseline",
        state="active",
        activated_on=date(2026, 11, 10),
        cutover_date=date(2026, 11, 10),
        **changes,
    )


@pytest.mark.integration
async def test_revision_owner_ordinal_and_single_active_constraints(db_session, owner, other_owner):
    from app.finance.loan_schedule_models import LoanScheduleRevision

    loan, _installment, receipt = await legacy_loan(db_session, owner.id)
    for fields in [
        {"user_id": other_owner.id},
        {"ordinal": 0},
        {"kind": "guessed"},
        {"state": "draft"},
    ]:
        data = {
            "user_id": owner.id,
            "loan_id": loan.id,
            "receipt_id": receipt.id,
            "ordinal": 1,
            "kind": "manual_baseline",
            "state": "active",
            "activated_on": date(2026, 11, 10),
            "cutover_date": date(2026, 11, 10),
        } | fields
        async with integrity_rejection(db_session):
            db_session.add(LoanScheduleRevision(**data))
            await db_session.flush()
    first = revision(LoanScheduleRevision, owner.id, loan.id, receipt.id)
    db_session.add(first)
    await db_session.flush()
    async with integrity_rejection(db_session):
        duplicate = revision(LoanScheduleRevision, owner.id, loan.id, receipt.id)
        duplicate.ordinal = 2
        db_session.add(duplicate)
        await db_session.flush()
    async with integrity_rejection(db_session):
        duplicate = revision(LoanScheduleRevision, owner.id, loan.id, receipt.id)
        duplicate.state = "superseded"
        db_session.add(duplicate)
        await db_session.flush()


@pytest.mark.integration
async def test_membership_cannot_reference_foreign_or_other_loan_installments(
    db_session, owner, other_owner
):
    from app.finance.loan_schedule_models import LoanScheduleMembership, LoanScheduleRevision

    loan, item, receipt = await legacy_loan(db_session, owner.id)
    _other_loan, other, _ = await legacy_loan(db_session, other_owner.id)
    _same_owner_loan, different_loan, _ = await legacy_loan(db_session, owner.id)
    rev = revision(LoanScheduleRevision, owner.id, loan.id, receipt.id)
    db_session.add(rev)
    await db_session.flush()
    values = {
        "user_id": owner.id,
        "loan_id": loan.id,
        "revision_id": rev.id,
        "installment_id": item.id,
        "due_date": item.due_date,
        "principal_pln": item.principal_pln,
        "interest_pln": item.interest_pln,
        "fees_pln": item.fees_pln,
    }
    for change in [
        {"installment_id": other.id},
        {"installment_id": different_loan.id},
        {"principal_pln": -1},
        {"bank_number": 0},
    ]:
        async with integrity_rejection(db_session):
            db_session.add(LoanScheduleMembership(**(values | change)))
            await db_session.flush()
    membership = LoanScheduleMembership(**values)
    db_session.add(membership)
    await db_session.flush()
    assert membership.bank_number is None and membership.source_row_id is None
    async with integrity_rejection(db_session):
        db_session.add(LoanScheduleMembership(**values))
        await db_session.flush()


@pytest.mark.integration
async def test_revision_pointers_are_bound_to_the_same_owner_and_loan(db_session, owner):
    from app.finance.loan_schedule_models import LoanScheduleRevision

    first, installment, receipt = await legacy_loan(db_session, owner.id)
    second, _other, _ = await legacy_loan(db_session, owner.id)
    rev = revision(LoanScheduleRevision, owner.id, first.id, receipt.id)
    db_session.add(rev)
    await db_session.flush()
    async with integrity_rejection(db_session):
        second.active_schedule_revision_id = rev.id
        await db_session.flush()
    async with integrity_rejection(db_session):
        installment.superseded_by_revision_id = uuid.uuid4()
        await db_session.flush()
