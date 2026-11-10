"""Single active-plan predicate; NULL preserves the entire legacy plan."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.finance.loan_schedule_models import LoanScheduleMembership, LoanScheduleRevision
from app.finance.models import LoanInstallment


class ScheduleMutationConflict(ValueError):
    """The caller must import a new version, not rewrite existing source history."""


def active_installment_predicate() -> ColumnElement[bool]:
    return LoanInstallment.superseded_by_revision_id.is_(None)


def assert_active_installment(item: LoanInstallment) -> None:
    if item.superseded_by_revision_id is not None:
        raise ScheduleMutationConflict(
            "Installment superseded; import a new schedule version instead"
        )


async def assert_manual_schedule_mutation(
    db: AsyncSession,
    owner: uuid.UUID,
    loan_id: uuid.UUID,
    active_revision_id: uuid.UUID | None,
    item: LoanInstallment | None = None,
) -> None:
    if item is not None:
        assert_active_installment(item)
    bank_managed = (
        await db.scalar(
            select(LoanScheduleRevision.id).where(
                LoanScheduleRevision.id == active_revision_id,
                LoanScheduleRevision.user_id == owner,
                LoanScheduleRevision.loan_id == loan_id,
                LoanScheduleRevision.kind == "bank_import",
            )
        )
        if active_revision_id is not None
        else None
    )
    if bank_managed is None and item is not None:
        bank_managed = await db.scalar(
            select(LoanScheduleRevision.id)
            .join(
                LoanScheduleMembership,
                LoanScheduleMembership.revision_id == LoanScheduleRevision.id,
            )
            .where(
                LoanScheduleRevision.user_id == owner,
                LoanScheduleRevision.loan_id == loan_id,
                LoanScheduleRevision.kind == "bank_import",
                LoanScheduleMembership.installment_id == item.id,
            )
            .limit(1)
        )
    if bank_managed is not None:
        raise ScheduleMutationConflict(
            "Bank-managed plan is immutable; import a new schedule version instead"
        )
