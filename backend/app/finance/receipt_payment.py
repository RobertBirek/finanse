"""One receipt, one already allocated whole payment; human category-only authority."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.categorization import _record_human_assignment, _write_category_parts
from app.finance.categorization_context import (
    CategorizationError,
    LedgerContext,
    build_preview,
    columns,
    digest,
    load_context,
)
from app.finance.models import DocumentPaymentAllocation, FinanceCommandReceipt, Posting
from app.finance.proposal_state import supersede_pending_proposals
from app.finance.receipt_approval import validate_approved_receipt
from app.finance.receipt_commands import ReceiptCommandOutcome, run_receipt_command
from app.finance.receipt_context import ReceiptDomainContext, load_receipt_context
from app.finance.receipt_math import calculate_receipt
from app.finance.receipt_schemas import (
    ReceiptApplicationStatus,
    ReceiptCalculation,
    ReceiptPaymentApply,
    ReceiptPaymentContext,
    ReceiptPaymentPreview,
    ReceiptPaymentRequest,
    ReceiptPaymentResult,
    ReceiptRevisionView,
)
from app.finance.rule_policy import get_settings

ACTION = "apply_receipt_item_split"


@dataclass
class ReceiptPaymentDomain:
    ctx: ReceiptDomainContext
    revision: ReceiptRevisionView
    ledger: LedgerContext
    allocations: list[DocumentPaymentAllocation]
    calculation: ReceiptCalculation


async def load_receipt_payment(
    db: AsyncSession, owner: uuid.UUID, bill_id: uuid.UUID, *, lock: bool
) -> ReceiptPaymentDomain:
    ctx = await load_receipt_context(db, owner, bill_id, lock=lock)
    if not ctx.state or not ctx.approved or ctx.draft:
        raise CategorizationError(
            "revision_required", "Zatwierdź aktualne pozycje paragonu i zamknij szkic."
        )
    if validate_approved_receipt(ctx, ctx.approved):
        raise CategorizationError(
            "items_changed",
            "Pozycje, nagłówek, sklep lub kategorie wymagają ponownego sprawdzenia.",
        )
    rows = list(
        (
            await db.scalars(
                select(DocumentPaymentAllocation)
                .where(DocumentPaymentAllocation.financial_document_id == bill_id)
                .order_by(DocumentPaymentAllocation.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if len(rows) != 1 or rows[0].user_id != owner:
        raise CategorizationError(
            "full_payment_required",
            "Podział wymaga jednej pełnej alokacji do jednej własnej płatności PLN.",
        )
    posting_id = rows[0].posting_id
    all_allocations = list(
        (
            await db.scalars(
                select(DocumentPaymentAllocation)
                .where(
                    or_(
                        DocumentPaymentAllocation.financial_document_id == bill_id,
                        DocumentPaymentAllocation.posting_id == posting_id,
                    )
                )
                .order_by(DocumentPaymentAllocation.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if len(all_allocations) != 1:
        raise CategorizationError(
            "shared_payment", "Ta płatność jest przypisana także do innego dokumentu."
        )
    txn_id = await db.scalar(select(Posting.transaction_id).where(Posting.id == posting_id))
    if txn_id is None:
        raise CategorizationError("payment_missing", "Powiązana płatność nie istnieje.")
    try:
        ledger = await load_context(db, owner, txn_id, lock=lock)
    except LookupError as error:
        raise CategorizationError(
            "payment_missing", "Powiązana własna płatność nie istnieje."
        ) from error
    eligibility = ledger.eligibility()
    if not eligibility.allowed:
        raise CategorizationError(
            eligibility.reason_code or "protected", eligibility.message or "Płatność chroniona."
        )
    account = next(p for p in ledger.txn.postings if p.account_id)
    if (
        account.id != posting_id
        or account.source_amount != rows[0].amount_minor
        or ctx.bill.total_minor != account.source_amount
    ):
        raise CategorizationError(
            "full_payment_required", "Kwota paragonu, alokacji i całej płatności musi się zgadzać."
        )
    assert ctx.bill.total_minor is not None
    calc = calculate_receipt(ctx.approved.body, expected_total_minor=ctx.bill.total_minor)
    if calc.problems:
        raise CategorizationError("incomplete_receipt", "Sprawdź sumę i kategorie pozycji.")
    return ReceiptPaymentDomain(ctx, ctx.approved, ledger, all_allocations, calc)


async def _preview(
    db: AsyncSession, owner: uuid.UUID, bill_id: uuid.UUID, data: ReceiptPaymentRequest
) -> tuple[ReceiptPaymentDomain, ReceiptPaymentPreview]:
    domain = await load_receipt_payment(db, owner, bill_id, lock=True)
    ctx = domain.ctx
    assert ctx.state is not None
    if (
        ctx.state.version != data.expected_state_version
        or domain.revision.id != data.approved_revision_id
    ):
        raise CategorizationError("version_conflict", "Zatwierdzone pozycje zmieniły się.")
    native = build_preview(domain.ledger, domain.calculation.parts)
    policy = await get_settings(db, owner)
    token = digest(
        {
            "owner": owner,
            "bill": columns(ctx.bill),
            "state_version": ctx.state.version,
            "revision": domain.revision.id,
            "body": domain.revision.body_sha256,
            "store_version": domain.revision.body.store_version,
            "categories": [
                columns(c) for c in sorted(ctx.categories.values(), key=lambda c: str(c.id))
            ],
            "policy": columns(policy) if policy else None,
            "allocations": [columns(a) for a in domain.allocations],
            "ledger": domain.ledger.snapshot(),
            "native_preview": native.preview_snapshot,
            "calculation": domain.calculation.model_dump(mode="json"),
        }
    )
    assert ctx.bill.total_minor is not None
    return domain, ReceiptPaymentPreview(
        expected_state_version=ctx.state.version,
        approved_revision_id=domain.revision.id,
        transaction_id=domain.ledger.txn.id,
        context_snapshot=domain.ledger.snapshot(),
        preview_snapshot=token,
        before_parts=native.before_parts,
        after_parts=native.after_parts,
        target_paths=native.target_paths,
        line_nets=domain.calculation.line_nets,
        body_sha256=domain.revision.body_sha256,
        total_minor=ctx.bill.total_minor,
    )


async def preview_receipt_payment(
    db: AsyncSession, owner: uuid.UUID, bill_id: uuid.UUID, data: ReceiptPaymentRequest
) -> ReceiptPaymentPreview:
    _, preview = await _preview(db, owner, bill_id, data)
    return preview


async def apply_receipt_payment(
    db: AsyncSession,
    owner: uuid.UUID,
    bill_id: uuid.UUID,
    data: ReceiptPaymentApply,
    *,
    idempotency_key: str,
) -> ReceiptPaymentResult:
    async def operation(receipt_id: uuid.UUID) -> ReceiptCommandOutcome:
        domain, preview = await _preview(db, owner, bill_id, data)
        if preview.preview_snapshot != data.expected_preview_snapshot:
            raise CategorizationError(
                "preview_conflict", "Podgląd podziału zmienił się; sprawdź go ponownie."
            )
        ledger = domain.ledger
        before = ledger.response()
        state = domain.ctx.state
        assert state is not None
        await _write_category_parts(db, ledger, preview.after_parts)
        await _record_human_assignment(
            db, ledger, before=before, parts=preview.after_parts, origin="manual"
        )
        await supersede_pending_proposals(db, owner, ledger.txn.id)
        state.version += 1
        state.last_apply_receipt_id = receipt_id
        await db.flush()
        grant = {
            "bill_id": str(bill_id),
            "revision_id": str(domain.revision.id),
            "body_sha256": domain.revision.body_sha256,
            "transaction_id": str(ledger.txn.id),
            "before_context_sha256": before.context_snapshot,
            "after_context_sha256": ledger.snapshot(),
            "preview_snapshot": preview.preview_snapshot,
            "store_id": str(domain.revision.body.store_id),
            "store_version": domain.revision.body.store_version,
            "approved_by": str(owner),
            "approved_at": datetime.now(UTC).isoformat(),
            "body": domain.revision.body.model_dump(mode="json"),
            "line_nets": [r.model_dump(mode="json") for r in domain.calculation.line_nets],
            "before_parts": [r.model_dump(mode="json") for r in preview.before_parts],
            "after_parts": [r.model_dump(mode="json") for r in preview.after_parts],
        }
        response = ReceiptPaymentResult(
            context=ledger.response(),
            state_version=state.version,
            receipt_id=receipt_id,
            revision_id=domain.revision.id,
            grant=grant,
        )
        return ReceiptCommandOutcome(
            response, bill_id, state.version, [ledger.txn.id, domain.revision.id]
        )

    return ReceiptPaymentResult.model_validate(
        await run_receipt_command(
            db,
            owner,
            action=ACTION,
            key=idempotency_key,
            payload={"bill_id": str(bill_id), **data.model_dump(mode="json")},
            operation=operation,
        )
    )


async def get_receipt_payment_context(
    db: AsyncSession, owner: uuid.UUID, bill_id: uuid.UUID
) -> ReceiptPaymentContext:
    ctx = await load_receipt_context(db, owner, bill_id)
    last = None
    if ctx.state and ctx.state.last_apply_receipt_id:
        receipt = await db.scalar(
            select(FinanceCommandReceipt).where(
                FinanceCommandReceipt.id == ctx.state.last_apply_receipt_id,
                FinanceCommandReceipt.user_id == owner,
                FinanceCommandReceipt.entity_id == bill_id,
                FinanceCommandReceipt.action == ACTION,
            )
        )
        if receipt:
            result = ReceiptPaymentResult.model_validate(receipt.response_json)
            try:
                ledger = await load_context(db, owner, result.context.transaction_id)
                changed = ledger.snapshot() != result.grant["after_context_sha256"]
            except LookupError:
                changed = True
            last = ReceiptApplicationStatus(
                receipt_id=receipt.id,
                revision_id=result.revision_id,
                transaction_id=result.context.transaction_id,
                items_changed=bool(ctx.draft)
                or not ctx.approved
                or not ctx.approved.current
                or ctx.approved.id != result.revision_id
                or ctx.approved.body_sha256 != result.grant["body_sha256"],
                ledger_changed=changed,
            )
    try:
        await load_receipt_payment(db, owner, bill_id, lock=False)
        return ReceiptPaymentContext(allowed=True, blocked_reason=None, last_application=last)
    except CategorizationError as error:
        return ReceiptPaymentContext(
            allowed=False, blocked_reason=str(error), last_application=last
        )
