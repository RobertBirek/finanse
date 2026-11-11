"""Owned immutable activation discovery and semantic reparse comparison, no mutations."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.imports.contracts import ParsedSchedule
from app.finance.imports.errors import ImportError
from app.finance.imports.models import ImportRevision, ImportSource
from app.finance.loan_schedule_models import LoanScheduleRevision
from app.finance.loan_schedule_schemas import ScheduleCommitResult, ScheduleSourceActivation
from app.finance.models import FinanceCommandReceipt


async def source_activations(
    db: AsyncSession, owner: uuid.UUID, batch_id: uuid.UUID
) -> dict[uuid.UUID, list[ScheduleSourceActivation]]:
    records = (
        await db.execute(
            select(ImportSource, LoanScheduleRevision, FinanceCommandReceipt)
            .join(ImportRevision, ImportRevision.source_id == ImportSource.id)
            .join(
                LoanScheduleRevision, LoanScheduleRevision.source_revision_id == ImportRevision.id
            )
            .join(
                FinanceCommandReceipt, FinanceCommandReceipt.id == LoanScheduleRevision.receipt_id
            )
            .where(
                ImportSource.user_id == owner,
                ImportSource.batch_id == batch_id,
                ImportSource.kind == "loan_schedule",
                ImportRevision.user_id == owner,
                ImportRevision.batch_id == batch_id,
                LoanScheduleRevision.user_id == owner,
                LoanScheduleRevision.kind == "bank_import",
                FinanceCommandReceipt.user_id == owner,
                FinanceCommandReceipt.entity_id == batch_id,
                FinanceCommandReceipt.action == "loan_schedule.activate",
            )
            .order_by(LoanScheduleRevision.ordinal.desc())
        )
    ).all()
    result: dict[uuid.UUID, list[ScheduleSourceActivation]] = {}
    for source, revision, receipt in records:
        # get_batch also runs before this transaction finalizes its new receipt.
        if not receipt.response_json:
            continue
        value = ScheduleCommitResult.model_validate(receipt.response_json)
        if (
            value.receipt_id != receipt.id
            or value.batch_id != batch_id
            or value.revision_id != revision.id
            or value.loan_id != revision.loan_id
        ):
            raise ImportError(
                "schedule_receipt_inconsistent", "Niespójne potwierdzenie wersji harmonogramu."
            )
        assert revision.source_revision_id is not None
        result.setdefault(source.id, []).append(
            ScheduleSourceActivation(source_revision_id=revision.source_revision_id, result=value)
        )
    return result


def schedule_semantics(parsed: ParsedSchedule) -> dict[str, object]:
    """Parser version/physical row location may change; bank facts must not."""
    return {
        "bank": parsed.bank,
        "layout": parsed.layout,
        "currency": parsed.currency,
        "loan_reference": parsed.loan_reference,
        "effective_date": parsed.effective_date,
        "complete_tail": parsed.complete_tail,
        "rows": [row.model_dump(exclude={"position"}) for row in parsed.rows],
    }
