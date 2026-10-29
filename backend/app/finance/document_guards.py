"""Guards that keep ledger rows referenced by document allocations immutable."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.models import DocumentPaymentAllocation, FinancialTransaction, Posting


async def lock_document_mutations(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Take the shared owner allocation lock before taking ledger row locks."""
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"bill-allocation:{user_id}")))
    )


async def guard_allocated_transaction_change(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID, changes: dict[str, object]
) -> None:
    """Reject identity changes to a transaction whose posting is allocated to a bill."""
    # Narrative edits do not alter the allocated payment's identity.
    if not changes or set(changes) <= {"description"}:
        return
    transaction = await db.scalar(
        select(FinancialTransaction).where(
            FinancialTransaction.id == transaction_id, FinancialTransaction.user_id == user_id
        )
    )
    if transaction is None:
        return
    identity_change = "delete" in changes or any(
        key not in {"description", "transaction_date", "is_pending"}
        or (key == "transaction_date" and value != transaction.date)
        or (key == "is_pending" and value != transaction.is_pending)
        for key, value in changes.items()
    )
    if not identity_change:
        return
    allocated = await db.scalar(
        select(DocumentPaymentAllocation.id)
        .join(Posting, Posting.id == DocumentPaymentAllocation.posting_id)
        .join(FinancialTransaction, FinancialTransaction.id == Posting.transaction_id)
        .where(FinancialTransaction.id == transaction_id, FinancialTransaction.user_id == user_id)
        .limit(1)
    )
    if allocated is not None:
        raise ValueError("Cannot change or delete a transaction linked to a document payment")


async def guard_bill_account_change(
    db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID, changes: dict[str, object]
) -> None:
    """Prevent changing/deleting accounts referenced by a financial document."""
    from app.finance.models import FinancialDocument

    if not changes:
        return
    referenced = await db.scalar(
        select(FinancialDocument.id)
        .where(
            FinancialDocument.user_id == user_id, FinancialDocument.payment_account_id == account_id
        )
        .limit(1)
    )
    if referenced is not None:
        raise ValueError("Account is referenced by a financial document")
