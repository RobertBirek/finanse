"""Explicit, single-occurrence replacement of a recurring forecast estimate."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.finance.bills import _bill, _response, _run_bill_command
from app.finance.bills_schemas import (
    BillResponse,
    CoverageCandidate,
    CoverageDecision,
    MutationContext,
)
from app.finance.dates import _local_today
from app.finance.document_guards import lock_document_mutations
from app.finance.models import RecurringOccurrenceCoverage, ScheduledFinanceItem


async def get_coverage_candidates(
    db: AsyncSession, user_id: uuid.UUID, bill_id: uuid.UUID
) -> list[CoverageCandidate]:
    """Read-only candidates: the matching month, account and category are evidence, not proof."""
    bill = await _bill(db, user_id, bill_id)
    if bill is None:
        raise LookupError("bill_not_found")
    if bill.due_date is None or bill.payment_account_id is None or bill.category_id is None:
        return []
    items = list(
        (
            await db.execute(
                select(ScheduledFinanceItem)
                .where(
                    ScheduledFinanceItem.user_id == user_id,
                    ScheduledFinanceItem.is_active.is_(True),
                    ScheduledFinanceItem.type == "expense",
                    ScheduledFinanceItem.account_id == bill.payment_account_id,
                    ScheduledFinanceItem.category_id == bill.category_id,
                )
                .order_by(ScheduledFinanceItem.id)
            )
        ).scalars()
    )
    from app.finance.cashflow import _resolve_scheduled_amount

    return [
        CoverageCandidate(
            scheduled_item_id=item.id,
            occurrence_date=date(bill.due_date.year, bill.due_date.month, item.due_day),
            name=item.name,
            estimate_amount_pln=await _resolve_scheduled_amount(db, user_id, item, _local_today()),
        )
        for item in items
    ]


async def decide_coverage(
    db: AsyncSession,
    user_id: uuid.UUID,
    bill_id: uuid.UUID,
    data: CoverageDecision,
    *,
    context: MutationContext,
) -> BillResponse:
    async def operation() -> BillResponse:
        await lock_document_mutations(db, user_id)
        bill = await _bill(db, user_id, bill_id, lock=True)
        if bill is None:
            raise LookupError("bill_not_found")
        if bill.version != data.version:
            raise RuntimeError("version_conflict")
        if bill.review != "approved" or bill.lifecycle != "active" or bill.declaration != "payable":
            raise ValueError("bill_not_coverable")
        existing = await db.scalar(
            select(RecurringOccurrenceCoverage)
            .where(RecurringOccurrenceCoverage.financial_document_id == bill.id)
            .with_for_update()
        )
        if data.choice == "separate":
            if existing is not None:
                raise ValueError("coverage_already_exists")
            bill.recurring_decision = "separate"
        else:
            assert data.scheduled_item_id is not None and data.occurrence_date is not None
            item = await db.scalar(
                select(ScheduledFinanceItem)
                .where(
                    ScheduledFinanceItem.id == data.scheduled_item_id,
                    ScheduledFinanceItem.user_id == user_id,
                )
                .with_for_update()
            )
            if item is None:
                raise LookupError("scheduled_item_not_found")
            valid = (
                item.is_active
                and item.type == "expense"
                and bill.due_date is not None
                and bill.due_date.year == data.occurrence_date.year
                and bill.due_date.month == data.occurrence_date.month
                and item.due_day == data.occurrence_date.day
                and item.account_id == bill.payment_account_id
                and item.category_id == bill.category_id
            )
            if not valid:
                raise ValueError("coverage_candidate_not_eligible")
            occupied = await db.scalar(
                select(RecurringOccurrenceCoverage.id)
                .where(
                    RecurringOccurrenceCoverage.user_id == user_id,
                    RecurringOccurrenceCoverage.scheduled_item_id == item.id,
                    RecurringOccurrenceCoverage.occurrence_date == data.occurrence_date,
                )
                .with_for_update()
            )
            if occupied is not None:
                raise ValueError("coverage_occurrence_already_replaced")
            if existing is not None:
                raise ValueError("coverage_already_exists")
            db.add(
                RecurringOccurrenceCoverage(
                    user_id=user_id,
                    scheduled_item_id=item.id,
                    occurrence_date=data.occurrence_date,
                    financial_document_id=bill.id,
                )
            )
            bill.recurring_decision = None
        bill.version += 1
        await log_event(
            db,
            user_id,
            "financial_document",
            str(bill.id),
            "coverage_" + data.choice,
            new_state={"version": bill.version},
            performed_by=context.performed_by,
        )
        await db.flush()
        return await _response(db, bill)

    return await _run_bill_command(
        db,
        user_id,
        "decide_bill_coverage",
        context.idempotency_key,
        {"bill_id": str(bill_id), **data.model_dump(mode="json")},
        operation,
    )


async def unlink_coverage(
    db: AsyncSession,
    user_id: uuid.UUID,
    bill_id: uuid.UUID,
    expected_version: int,
    *,
    confirm_unlink: bool,
    context: MutationContext,
) -> BillResponse:
    if not confirm_unlink:
        raise ValueError("coverage_unlink_confirmation_required")

    async def operation() -> BillResponse:
        await lock_document_mutations(db, user_id)
        bill = await _bill(db, user_id, bill_id, lock=True)
        if bill is None:
            raise LookupError("bill_not_found")
        if bill.version != expected_version:
            raise RuntimeError("version_conflict")
        coverage = await db.scalar(
            select(RecurringOccurrenceCoverage)
            .where(RecurringOccurrenceCoverage.financial_document_id == bill.id)
            .with_for_update()
        )
        if coverage is None:
            raise LookupError("coverage_not_found")
        await db.delete(coverage)
        bill.version += 1
        await log_event(
            db,
            user_id,
            "financial_document",
            str(bill.id),
            "unlink_coverage",
            new_state={"version": bill.version},
            performed_by=context.performed_by,
        )
        await db.flush()
        return await _response(db, bill)

    return await _run_bill_command(
        db,
        user_id,
        "unlink_bill_coverage",
        context.idempotency_key,
        {"bill_id": str(bill_id), "expected_version": expected_version, "confirm_unlink": True},
        operation,
    )
