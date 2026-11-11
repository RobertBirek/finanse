"""One receipt-backed transaction for plan versions. No financial transaction creation."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.imports.commands import ImportCommandOutcome, run_import_command
from app.finance.imports.errors import ImportError
from app.finance.loan_schedule_models import LoanScheduleMembership, LoanScheduleRevision
from app.finance.loan_schedule_preview import load_confirmed_schedule
from app.finance.loan_schedule_schemas import (
    ScheduleActivateRequest,
    ScheduleCommitResult,
    ScheduleMembershipDTO,
    ScheduleRevisionDetailDTO,
    ScheduleRevisionDTO,
)
from app.finance.loans import create_loan
from app.finance.models import LoanAgreement, LoanInstallment


async def activate_schedule(
    db: AsyncSession, owner: uuid.UUID, batch_id: uuid.UUID, data: ScheduleActivateRequest, key: str
) -> ScheduleCommitResult:
    async def operation(receipt_id: uuid.UUID) -> ImportCommandOutcome:
        context, request = await load_confirmed_schedule(db, owner, batch_id, data)
        max_number = max((i.number for i in context.state.installments), default=0)
        if max_number + len(context.diff.new_rows) > 2147483647:
            raise ImportError(
                "schedule_number_overflow", "Brak miejsca na wewnętrzną numerację nowych rat."
            )
        loan_id = request.target.loan_id
        if loan_id is None:
            assert request.target.new_loan is not None
            loan = await create_loan(db, owner, request.target.new_loan)
            loan_id = loan.id
        else:
            existing_loan = await db.get(LoanAgreement, loan_id)
            assert existing_loan is not None
            loan = existing_loan
        previous_id = loan.active_schedule_revision_id
        ordinal = int(
            await db.scalar(
                select(func.coalesce(func.max(LoanScheduleRevision.ordinal), 0)).where(
                    LoanScheduleRevision.loan_id == loan_id, LoanScheduleRevision.user_id == owner
                )
            )
            or 0
        )
        if previous_id is None and context.state.installments:
            ordinal += 1
            baseline = LoanScheduleRevision(
                user_id=owner,
                loan_id=loan_id,
                ordinal=ordinal,
                kind="manual_baseline",
                state="superseded",
                receipt_id=receipt_id,
                activated_on=context.today,
                cutover_date=context.diff.cutover_date,
            )
            db.add(baseline)
            await db.flush()
            for baseline_item in context.state.installments:
                db.add(
                    LoanScheduleMembership(
                        user_id=owner,
                        loan_id=loan_id,
                        revision_id=baseline.id,
                        installment_id=baseline_item.id,
                        bank_number=None,
                        source_row_id=None,
                        due_date=baseline_item.due_date,
                        principal_pln=baseline_item.principal_pln,
                        interest_pln=baseline_item.interest_pln,
                        fees_pln=baseline_item.fees_pln,
                    )
                )
            previous_id = baseline.id
        elif previous_id is not None:
            previous = await db.get(LoanScheduleRevision, previous_id)
            assert previous is not None
            previous.state = "superseded"
        await db.flush()
        revision = LoanScheduleRevision(
            user_id=owner,
            loan_id=loan_id,
            ordinal=ordinal + 1,
            kind="bank_import",
            state="active",
            previous_revision_id=previous_id,
            source_revision_id=context.revision.id,
            receipt_id=receipt_id,
            bank_effective_date=context.parsed.effective_date,
            activated_on=context.today,
            cutover_date=context.diff.cutover_date,
        )
        db.add(revision)
        await db.flush()
        for item_id in context.diff.superseded_ids:
            old = await db.get(LoanInstallment, item_id)
            assert old is not None
            old.superseded_by_revision_id = revision.id
        reused = {i.id: i for i in context.state.installments if i.id in context.diff.reused_ids}
        new_ids = []
        source_rows = {row.source_key: row for row in context.rows}
        for row in context.parsed.rows:
            match = next(
                (
                    i
                    for i in reused.values()
                    if (i.due_date, i.principal_pln, i.interest_pln, i.fees_pln)
                    == (row.due_date, row.principal, row.interest, row.fees)
                ),
                None,
            )
            if match is None:
                max_number += 1
                item = LoanInstallment(
                    user_id=owner,
                    loan_id=loan_id,
                    number=max_number,
                    due_date=row.due_date,
                    principal_pln=row.principal,
                    interest_pln=row.interest,
                    fees_pln=row.fees,
                )
                db.add(item)
                await db.flush()
                item_id = item.id
                new_ids.append(item_id)
            else:
                item_id = match.id
            db.add(
                LoanScheduleMembership(
                    user_id=owner,
                    loan_id=loan_id,
                    revision_id=revision.id,
                    installment_id=item_id,
                    bank_number=row.bank_number,
                    source_row_id=source_rows[str(row.bank_number)].id,
                    due_date=row.due_date,
                    principal_pln=row.principal,
                    interest_pln=row.interest,
                    fees_pln=row.fees,
                    balance_after_pln=row.balance_after,
                )
            )
        loan.active_schedule_revision_id = revision.id
        context.batch.version += 1
        await db.flush()
        result = ScheduleCommitResult(
            receipt_id=receipt_id,
            batch_id=batch_id,
            request_hash=data.request_hash,
            loan_id=loan_id,
            revision_id=revision.id,
            reused_ids=context.diff.reused_ids,
            new_ids=new_ids,
            superseded_ids=context.diff.superseded_ids,
        )
        return ImportCommandOutcome(
            result,
            batch_id,
            context.batch.version,
            [loan_id, revision.id, *result.reused_ids, *new_ids],
        )

    result = await run_import_command(
        db,
        owner,
        action="loan_schedule.activate",
        key=key,
        batch_id=batch_id,
        payload=data.model_dump(mode="json"),
        operation=operation,
    )
    return ScheduleCommitResult.model_validate(result)


async def list_schedule_revisions(
    db: AsyncSession, owner: uuid.UUID, loan_id: uuid.UUID
) -> list[ScheduleRevisionDTO]:
    if (
        await db.scalar(
            select(LoanAgreement.id).where(
                LoanAgreement.id == loan_id, LoanAgreement.user_id == owner
            )
        )
        is None
    ):
        raise ImportError("loan_not_found", "Nie znaleziono kredytu.", 404)
    revisions = (
        await db.scalars(
            select(LoanScheduleRevision)
            .where(LoanScheduleRevision.loan_id == loan_id, LoanScheduleRevision.user_id == owner)
            .order_by(LoanScheduleRevision.ordinal.desc())
        )
    ).all()
    return [ScheduleRevisionDTO.model_validate(revision) for revision in revisions]


async def get_schedule_revision(
    db: AsyncSession, owner: uuid.UUID, loan_id: uuid.UUID, revision_id: uuid.UUID
) -> ScheduleRevisionDetailDTO | None:
    if (
        await db.scalar(
            select(LoanAgreement.id).where(
                LoanAgreement.id == loan_id, LoanAgreement.user_id == owner
            )
        )
        is None
    ):
        return None
    revision = await db.scalar(
        select(LoanScheduleRevision).where(
            LoanScheduleRevision.id == revision_id,
            LoanScheduleRevision.loan_id == loan_id,
            LoanScheduleRevision.user_id == owner,
        )
    )
    if revision is None:
        return None
    members = (
        await db.scalars(
            select(LoanScheduleMembership)
            .where(
                LoanScheduleMembership.revision_id == revision_id,
                LoanScheduleMembership.loan_id == loan_id,
                LoanScheduleMembership.user_id == owner,
            )
            .order_by(
                LoanScheduleMembership.due_date,
                LoanScheduleMembership.bank_number,
                LoanScheduleMembership.id,
            )
        )
    ).all()
    return ScheduleRevisionDetailDTO(
        **ScheduleRevisionDTO.model_validate(revision).model_dump(),
        installments=[ScheduleMembershipDTO.model_validate(m) for m in members],
    )
