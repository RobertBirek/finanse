"""Financial document register only; settlement and forecasting are later slices."""

import hashlib
import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any, cast

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.documents.models import Document, DocumentExtractionRevision
from app.documents.review_schemas import ReviewSuggestion
from app.finance.bills_schemas import (
    AllocationResponse,
    BillApprove,
    BillFilters,
    BillLifecycle,
    BillPage,
    BillResponse,
    BillUpdate,
    CoverageResponse,
    DuplicateCandidate,
    MutationContext,
    SourceResponse,
)
from app.finance.models import (
    Account,
    Category,
    DocumentPaymentAllocation,
    FinanceCommandReceipt,
    FinancialDocument,
    FinancialDocumentSource,
    RecurringOccurrenceCoverage,
)


def _canonical_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


async def _run_bill_command(
    db: AsyncSession,
    user_id: uuid.UUID,
    action: str,
    key: str,
    payload: dict[str, object],
    operation: Callable[[], Awaitable[BillResponse]],
) -> BillResponse:
    """Replay the original public snapshot; callers own the surrounding commit."""
    request_hash = _canonical_hash(payload)
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"bill-command:{user_id}:{action}:{key}")))
    )
    receipt = (
        await db.execute(
            select(FinanceCommandReceipt).where(
                FinanceCommandReceipt.user_id == user_id,
                FinanceCommandReceipt.action == action,
                FinanceCommandReceipt.key == key,
            )
        )
    ).scalar_one_or_none()
    if receipt is not None:
        if receipt.request_hash != request_hash:
            raise ValueError("idempotency_key_reused")
        return BillResponse.model_validate(receipt.response_json)
    response = await operation()
    snapshot = response.model_dump(mode="json")
    db.add(
        FinanceCommandReceipt(
            user_id=user_id,
            action=action,
            key=key,
            request_hash=request_hash,
            entity_id=response.id,
            result_ids=[str(response.id)],
            version=response.version,
            response_json=cast(dict[str, object], snapshot),
        )
    )
    return response


async def _bill(
    db: AsyncSession, user_id: uuid.UUID, bill_id: uuid.UUID, *, lock: bool = False
) -> FinancialDocument | None:
    stmt = select(FinancialDocument).where(
        FinancialDocument.id == bill_id, FinancialDocument.user_id == user_id
    )
    if lock:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def _response(db: AsyncSession, bill: FinancialDocument) -> BillResponse:
    sources = list(
        (
            await db.execute(
                select(FinancialDocumentSource)
                .where(
                    FinancialDocumentSource.financial_document_id == bill.id,
                )
                .order_by(FinancialDocumentSource.id)
            )
        ).scalars()
    )
    allocations = list(
        (
            await db.execute(
                select(DocumentPaymentAllocation).where(
                    DocumentPaymentAllocation.financial_document_id == bill.id,
                )
            )
        ).scalars()
    )
    coverage = (
        await db.execute(
            select(RecurringOccurrenceCoverage).where(
                RecurringOccurrenceCoverage.financial_document_id == bill.id,
            )
        )
    ).scalar_one_or_none()
    revision = (
        await db.execute(
            select(DocumentExtractionRevision.id)
            .join(
                FinancialDocumentSource,
                FinancialDocumentSource.document_id == DocumentExtractionRevision.document_id,
            )
            .where(FinancialDocumentSource.financial_document_id == bill.id)
            .order_by(DocumentExtractionRevision.revision.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    paid = sum(item.amount_minor for item in allocations)
    total = bill.total_minor or 0
    remaining = max(total - paid, 0)
    reconciliation = "full" if total and remaining == 0 else "partial" if paid else "none"
    return BillResponse(
        id=bill.id,
        kind=cast(Any, bill.kind),
        supplier_name=bill.supplier_name,
        supplier_tax_id=bill.supplier_tax_id,
        number=bill.number,
        issue_date=bill.issue_date,
        sale_date=bill.sale_date,
        due_date=bill.due_date,
        payee_iban=bill.payee_iban,
        description=bill.description,
        category_id=bill.category_id,
        payment_account_id=bill.payment_account_id,
        total_minor=bill.total_minor,
        currency=cast(Any, bill.currency),
        declaration=cast(Any, bill.declaration),
        lifecycle=cast(Any, bill.lifecycle),
        review=cast(Any, bill.review),
        version=bill.version,
        paid_minor=paid,
        remaining_minor=remaining,
        reconciliation=cast(Any, reconciliation),
        sources=[SourceResponse(document_id=item.document_id) for item in sources],
        allocations=[
            AllocationResponse(posting_id=item.posting_id, amount_minor=item.amount_minor)
            for item in allocations
        ],
        extraction_revision_id=revision,
        coverage=None
        if coverage is None
        else CoverageResponse(
            scheduled_item_id=coverage.scheduled_item_id,
            occurrence_date=coverage.occurrence_date,
            choice="replace",
        ),
        forecast_exclusion_reasons=[],
    )


async def prepare_bill(
    db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID, *, context: MutationContext
) -> BillResponse:
    async def operation() -> BillResponse:
        document = (
            await db.execute(
                select(Document)
                .where(Document.id == document_id, Document.user_id == user_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if document is None:
            raise LookupError("document_not_found")
        await db.execute(
            select(
                func.pg_advisory_xact_lock(func.hashtext(f"bill-source:{user_id}:{document_id}"))
            )
        )
        source = (
            await db.execute(
                select(FinancialDocumentSource).where(
                    FinancialDocumentSource.document_id == document_id
                )
            )
        ).scalar_one_or_none()
        if source is not None:
            existing = await _bill(db, user_id, source.financial_document_id)
            if existing is None:
                raise LookupError("bill_not_found")
            return await _response(db, existing)
        bill = FinancialDocument(user_id=user_id)
        revision = (
            await db.execute(
                select(DocumentExtractionRevision)
                .where(
                    DocumentExtractionRevision.document_id == document_id,
                    DocumentExtractionRevision.user_id == user_id,
                )
                .order_by(DocumentExtractionRevision.revision.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        # OCR suggestions are only non-financial draft hints. Amount and currency stay
        # unset until the human explicitly supplies approval data.
        if revision is not None and revision.status == "ready":
            try:
                suggestion = ReviewSuggestion.model_validate(revision.data)
            except ValueError:
                suggestion = None
            if suggestion is not None and suggestion.document_type in {"invoice", "receipt"}:
                fields = suggestion.fields
                bill.kind = suggestion.document_type
                bill.supplier_name = fields.supplier_name
                bill.supplier_tax_id = fields.supplier_tax_id
                bill.number = fields.number
                bill.description = fields.description
                bill.payee_iban = fields.payee_iban
                for name in ("issue_date", "sale_date", "due_date"):
                    value = getattr(fields, name)
                    if value is not None:
                        setattr(bill, name, date.fromisoformat(value))
        db.add(bill)
        await db.flush()
        db.add(
            FinancialDocumentSource(
                user_id=user_id, financial_document_id=bill.id, document_id=document_id
            )
        )
        await log_event(
            db,
            user_id,
            "financial_document",
            str(bill.id),
            "prepare",
            new_state={"document_id": str(document_id)},
            performed_by=context.performed_by,
        )
        return await _response(db, bill)

    return await _run_bill_command(
        db,
        user_id,
        "prepare_bill",
        context.idempotency_key,
        {"document_id": str(document_id)},
        operation,
    )


async def find_duplicate_bills(
    db: AsyncSession, user_id: uuid.UUID, data: BillApprove
) -> list[DuplicateCandidate]:
    stmt = select(FinancialDocument).where(
        FinancialDocument.user_id == user_id,
        FinancialDocument.review == "approved",
        FinancialDocument.currency == data.currency,
        FinancialDocument.total_minor == data.total_minor,
        FinancialDocument.lifecycle == "active",
    )
    candidates = list((await db.execute(stmt)).scalars())
    answer: list[DuplicateCandidate] = []
    tax_id = (data.supplier_tax_id or "").replace("-", "").replace(" ", "").upper()
    number = (data.number or "").strip().upper()
    supplier = data.supplier_name.strip().casefold()
    for candidate in candidates:
        candidate_tax = (candidate.supplier_tax_id or "").replace("-", "").replace(" ", "").upper()
        candidate_number = (candidate.number or "").strip().upper()
        reasons: list[str] = []
        same_date = data.issue_date is not None and candidate.issue_date == data.issue_date
        if (
            tax_id
            and number
            and tax_id == candidate_tax
            and number == candidate_number
            and same_date
        ):
            reasons.append("supplier_tax_id_number_currency_amount")
        elif (
            same_date
            and candidate.supplier_name
            and candidate.supplier_name.strip().casefold() == supplier
        ):
            reasons.append("supplier_amount_currency")
        if reasons:
            answer.append(DuplicateCandidate(id=candidate.id, reasons=reasons))
    return answer


async def _validate_links(
    db: AsyncSession, user_id: uuid.UUID, data: BillApprove | BillUpdate
) -> None:
    if data.category_id is not None:
        category = await db.get(Category, data.category_id)
        if category is None or category.user_id != user_id:
            raise LookupError("category_not_found")
    if data.payment_account_id is not None:
        account = await db.get(Account, data.payment_account_id)
        if account is None or account.user_id != user_id:
            raise LookupError("account_not_found")


async def approve_bill(
    db: AsyncSession,
    user_id: uuid.UUID,
    bill_id: uuid.UUID,
    data: BillApprove,
    *,
    context: MutationContext,
) -> BillResponse:
    async def operation() -> BillResponse:
        bill = await _bill(db, user_id, bill_id, lock=True)
        if bill is None:
            raise LookupError("bill_not_found")
        if bill.version != data.version:
            raise RuntimeError("version_conflict")
        if bill.review not in {"draft", "rejected"}:
            raise ValueError("bill_not_approvable")
        await _validate_links(db, user_id, data)
        duplicates = await find_duplicate_bills(db, user_id, data)
        if duplicates and data.duplicate_decision != "separate":
            raise ValueError("duplicate_decision_required")
        for name, value in data.model_dump(exclude={"version", "duplicate_decision"}).items():
            setattr(bill, name, value)
        bill.review = "approved"
        bill.version += 1
        await log_event(
            db,
            user_id,
            "financial_document",
            str(bill.id),
            "approve",
            new_state={
                "version": bill.version,
                "source_ids": [
                    str(s.document_id)
                    for s in (
                        await db.execute(
                            select(FinancialDocumentSource).where(
                                FinancialDocumentSource.financial_document_id == bill.id
                            )
                        )
                    ).scalars()
                ],
            },
            performed_by=context.performed_by,
        )
        return await _response(db, bill)

    return await _run_bill_command(
        db,
        user_id,
        "approve_bill",
        context.idempotency_key,
        {"bill_id": str(bill_id), **data.model_dump(mode="json")},
        operation,
    )


async def update_bill(
    db: AsyncSession,
    user_id: uuid.UUID,
    bill_id: uuid.UUID,
    data: BillUpdate,
    *,
    context: MutationContext,
) -> BillResponse:
    async def operation() -> BillResponse:
        bill = await _bill(db, user_id, bill_id, lock=True)
        if bill is None:
            raise LookupError("bill_not_found")
        if bill.version != data.expected_version:
            raise RuntimeError("version_conflict")
        values = data.model_dump(exclude_unset=True, exclude={"expected_version"})
        await _validate_links(db, user_id, data)
        allocated = await db.scalar(
            select(func.coalesce(func.sum(DocumentPaymentAllocation.amount_minor), 0)).where(
                DocumentPaymentAllocation.financial_document_id == bill.id
            )
        )
        if values.get("total_minor") is not None and values["total_minor"] < allocated:
            raise ValueError("total_below_paid")
        if "currency" in values and values["currency"] != bill.currency and allocated:
            raise ValueError("currency_change_with_allocations")
        for name, value in values.items():
            setattr(bill, name, value)
        if bill.review == "approved" and any(
            getattr(bill, field) is None
            for field in ("kind", "supplier_name", "description", "total_minor", "currency")
        ):
            raise ValueError("approved_bill_incomplete")
        bill.version += 1
        await log_event(
            db,
            user_id,
            "financial_document",
            str(bill.id),
            "update",
            new_state={"version": bill.version, "fields": sorted(values)},
            performed_by=context.performed_by,
        )
        return await _response(db, bill)

    return await _run_bill_command(
        db,
        user_id,
        "update_bill",
        context.idempotency_key,
        {"bill_id": str(bill_id), **data.model_dump(mode="json", exclude_unset=True)},
        operation,
    )


async def attach_source(
    db: AsyncSession,
    user_id: uuid.UUID,
    bill_id: uuid.UUID,
    document_id: uuid.UUID,
    expected_version: int,
    *,
    context: MutationContext,
) -> BillResponse:
    async def operation() -> BillResponse:
        document = (
            await db.execute(
                select(Document)
                .where(Document.id == document_id, Document.user_id == user_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if document is None:
            raise LookupError("document_not_found")
        await db.execute(
            select(
                func.pg_advisory_xact_lock(func.hashtext(f"bill-source:{user_id}:{document_id}"))
            )
        )
        source = (
            await db.execute(
                select(FinancialDocumentSource)
                .where(FinancialDocumentSource.document_id == document_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        ids = sorted({bill_id, source.financial_document_id} if source else {bill_id}, key=str)
        bills = {
            item.id: item
            for item in (
                await db.execute(
                    select(FinancialDocument)
                    .where(FinancialDocument.id.in_(ids), FinancialDocument.user_id == user_id)
                    .order_by(FinancialDocument.id)
                    .with_for_update()
                )
            ).scalars()
        }
        bill = bills.get(bill_id)
        moved_from_id: uuid.UUID | None = None
        if bill is None:
            raise LookupError("bill_not_found")
        if bill.version != expected_version:
            raise RuntimeError("version_conflict")
        if source is not None and source.financial_document_id != bill.id:
            old = bills.get(source.financial_document_id)
            old_bill_id = source.financial_document_id
            moved_from_id = old_bill_id
            allocations = await db.scalar(
                select(func.count())
                .select_from(DocumentPaymentAllocation)
                .where(
                    DocumentPaymentAllocation.financial_document_id == source.financial_document_id
                )
            )
            coverage = await db.scalar(
                select(func.count())
                .select_from(RecurringOccurrenceCoverage)
                .where(
                    RecurringOccurrenceCoverage.financial_document_id
                    == source.financial_document_id
                )
            )
            if old is None or old.review not in {"draft", "rejected"} or allocations or coverage:
                raise ValueError("source_cannot_be_moved")
            source.financial_document_id = bill.id
            old.version += 1
            await log_event(
                db,
                user_id,
                "financial_document",
                str(old.id),
                "detach_source",
                new_state={
                    "document_id": str(document_id),
                    "from_bill_id": str(old_bill_id),
                    "to_bill_id": str(bill.id),
                    "version": old.version,
                },
                performed_by=context.performed_by,
            )
        elif source is None:
            db.add(
                FinancialDocumentSource(
                    user_id=user_id, financial_document_id=bill.id, document_id=document_id
                )
            )
        bill.version += 1
        await log_event(
            db,
            user_id,
            "financial_document",
            str(bill.id),
            "attach_source",
            new_state={
                "document_id": str(document_id),
                "from_bill_id": str(moved_from_id) if moved_from_id is not None else None,
                "to_bill_id": str(bill.id),
                "version": bill.version,
            },
            performed_by=context.performed_by,
        )
        return await _response(db, bill)

    return await _run_bill_command(
        db,
        user_id,
        "attach_bill_source",
        context.idempotency_key,
        {
            "bill_id": str(bill_id),
            "document_id": str(document_id),
            "expected_version": expected_version,
        },
        operation,
    )


async def set_bill_lifecycle(
    db: AsyncSession,
    user_id: uuid.UUID,
    bill_id: uuid.UUID,
    lifecycle: BillLifecycle,
    expected_version: int,
    *,
    context: MutationContext,
) -> BillResponse:
    async def operation() -> BillResponse:
        bill = await _bill(db, user_id, bill_id, lock=True)
        if bill is None:
            raise LookupError("bill_not_found")
        if bill.version != expected_version:
            raise RuntimeError("version_conflict")
        if bill.lifecycle != lifecycle:
            bill.lifecycle = lifecycle
            bill.version += 1
            await log_event(
                db,
                user_id,
                "financial_document",
                str(bill.id),
                f"lifecycle_{lifecycle}",
                new_state={"version": bill.version},
                performed_by=context.performed_by,
            )
        return await _response(db, bill)

    return await _run_bill_command(
        db,
        user_id,
        "set_bill_lifecycle",
        context.idempotency_key,
        {"bill_id": str(bill_id), "lifecycle": lifecycle, "expected_version": expected_version},
        operation,
    )


async def get_bill(db: AsyncSession, user_id: uuid.UUID, bill_id: uuid.UUID) -> BillResponse | None:
    bill = await _bill(db, user_id, bill_id)
    return None if bill is None else await _response(db, bill)


async def list_bills(
    db: AsyncSession, user_id: uuid.UUID, *, limit: int, offset: int, filters: BillFilters
) -> BillPage:
    stmt = select(FinancialDocument).where(FinancialDocument.user_id == user_id)
    for field in ("kind", "review", "declaration", "lifecycle"):
        value = getattr(filters, field)
        if value is not None:
            stmt = stmt.where(getattr(FinancialDocument, field) == value)
    if filters.due_from:
        stmt = stmt.where(FinancialDocument.due_date >= filters.due_from)
    if filters.due_to:
        stmt = stmt.where(FinancialDocument.due_date <= filters.due_to)
    if filters.query:
        stmt = stmt.where(
            or_(
                FinancialDocument.supplier_name.ilike(f"%{filters.query}%"),
                FinancialDocument.number.ilike(f"%{filters.query}%"),
                FinancialDocument.description.ilike(f"%{filters.query}%"),
            )
        )
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    bills = list(
        (
            await db.execute(
                stmt.order_by(FinancialDocument.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars()
    )
    return BillPage(
        items=[await _response(db, item) for item in bills],
        total=total or 0,
        limit=limit,
        offset=offset,
    )
