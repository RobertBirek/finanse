"""User declarations change obligations, not ledger evidence or account balances."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.finance.bills import _bill, _response, _run_bill_command
from app.finance.bills_schemas import BillDeclarationChange, BillResponse, MutationContext
from app.finance.document_guards import lock_document_mutations
from app.finance.models import DocumentPaymentAllocation


async def set_bill_payment_declaration(
    db: AsyncSession,
    user_id: uuid.UUID,
    bill_id: uuid.UUID,
    data: BillDeclarationChange,
    *,
    context: MutationContext,
) -> BillResponse:
    async def operation() -> BillResponse:
        await lock_document_mutations(db, user_id)
        bill = await _bill(db, user_id, bill_id, lock=True)
        if bill is None:
            raise LookupError("bill_not_found")
        if bill.version != data.expected_version:
            raise RuntimeError("version_conflict")
        if (
            bill.review != "approved"
            or bill.lifecycle != "active"
            or bill.currency not in {"PLN", "EUR", "USD"}
        ):
            raise ValueError("bill_not_declarable")
        paid = int(
            await db.scalar(
                select(func.coalesce(func.sum(DocumentPaymentAllocation.amount_minor), 0)).where(
                    DocumentPaymentAllocation.financial_document_id == bill.id
                )
            )
            or 0
        )
        remaining = max((bill.total_minor or 0) - paid, 0)
        if remaining <= 0:
            raise ValueError("bill_already_reconciled")
        if bill.declaration == data.declaration:
            return await _response(db, bill)
        old_state = {"declaration": bill.declaration, "version": bill.version}
        bill.declaration = data.declaration
        bill.version += 1
        await log_event(
            db,
            user_id,
            "financial_document",
            str(bill.id),
            "payment_declaration",
            old_state=old_state,
            new_state={
                "declaration": bill.declaration,
                "version": bill.version,
                "remaining_minor": remaining,
                "currency": bill.currency,
                "without_transaction": True,
            },
            performed_by=context.performed_by,
        )
        return await _response(db, bill)

    return await _run_bill_command(
        db,
        user_id,
        "set_bill_payment_declaration",
        context.idempotency_key,
        {"bill_id": str(bill_id), **data.model_dump(mode="json")},
        operation,
    )
