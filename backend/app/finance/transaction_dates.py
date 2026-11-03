"""Explicit, owned manual date evidence; no inference and no monetary writes."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.audit.service import log_event
from app.finance.document_guards import guard_allocated_transaction_change, lock_document_mutations
from app.finance.models import (
    ActualImportMapping,
    FinancialTransaction,
    LoanPaymentLink,
    TransactionDateMetadata,
)
from app.finance.schemas import TransactionDatesUpdate


class TransactionDateError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(detail)


def purchase_date_expression() -> ColumnElement[date]:
    return func.coalesce(TransactionDateMetadata.purchase_date, FinancialTransaction.date)


def _state(meta: TransactionDateMetadata | None) -> dict[str, Any] | None:
    if meta is None:
        return None
    return {
        "purchase_date": meta.purchase_date.isoformat() if meta.purchase_date else None,
        "booking_date": meta.booking_date.isoformat() if meta.booking_date else None,
        "purchase_date_source": meta.purchase_date_source,
        "booking_date_source": meta.booking_date_source,
        "version": meta.version,
    }


async def add_manual_date_metadata(
    db: AsyncSession, txn: FinancialTransaction, purchase: date | None, booking: date
) -> None:
    meta = TransactionDateMetadata(
        transaction_id=txn.id,
        user_id=txn.user_id,
        purchase_date=purchase,
        purchase_date_source="manual" if purchase else None,
        booking_date=booking,
        booking_date_source="manual",
        version=1,
    )
    txn.date_metadata = meta
    db.add(meta)
    await log_event(
        db,
        txn.user_id,
        "financial_transaction",
        str(txn.id),
        "set_transaction_dates",
        new_state=_state(meta),
    )
    await db.flush()


async def set_transaction_dates(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID, data: TransactionDatesUpdate
) -> FinancialTransaction | None:
    await lock_document_mutations(db, user_id)
    txn = await db.scalar(
        select(FinancialTransaction)
        .options(selectinload(FinancialTransaction.postings))
        .where(FinancialTransaction.id == transaction_id, FinancialTransaction.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if txn is None:
        return None
    mapped = await db.scalar(
        select(ActualImportMapping.id)
        .where(
            ActualImportMapping.user_id == user_id,
            ActualImportMapping.entity_type == "transaction",
            ActualImportMapping.entity_id == transaction_id,
        )
        .limit(1)
    )
    linked = await db.scalar(
        select(LoanPaymentLink.id).where(LoanPaymentLink.transaction_id == transaction_id).limit(1)
    )
    if txn.type != "expense" or txn.source != "manual" or mapped is not None or linked is not None:
        raise TransactionDateError(
            "date_protected",
            "Daty importu lub powiązanej płatności są chronione. Ta korekta obsługuje ręczne wydatki.",
        )
    try:
        await guard_allocated_transaction_change(
            db, user_id, transaction_id, {"explicit_dates": True}
        )
    except ValueError as error:
        raise TransactionDateError(
            "date_protected", "Daty płatności powiązanej z dokumentem są chronione."
        ) from error
    meta = await db.scalar(
        select(TransactionDateMetadata)
        .where(TransactionDateMetadata.transaction_id == transaction_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        data.expected_version != (meta.version if meta else 0)
        or data.expected_updated_at != txn.updated_at
    ):
        raise TransactionDateError(
            "date_version_conflict",
            "Dane transakcji zmieniły się. Odśwież je i ponownie sprawdź daty.",
        )
    if meta and meta.purchase_date == data.purchase_date and meta.booking_date == data.booking_date:
        return txn
    before = _state(meta)
    if meta is None:
        await add_manual_date_metadata(db, txn, data.purchase_date, data.booking_date)
    else:
        meta.purchase_date = data.purchase_date
        meta.purchase_date_source = "manual" if data.purchase_date else None
        meta.booking_date = data.booking_date
        meta.booking_date_source = "manual"
        meta.version += 1
        await log_event(
            db,
            user_id,
            "financial_transaction",
            str(transaction_id),
            "set_transaction_dates",
            old_state=before,
            new_state=_state(meta),
        )
    # This is an explicit manual decision, never a historical backfill.
    if txn.date != data.booking_date:
        txn.date = data.booking_date
    await db.flush()
    await db.refresh(txn, attribute_names=["updated_at", "date_metadata"])
    return txn
