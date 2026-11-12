"""Atomic category-only mutation with manual provenance and durable replay."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.finance.categorization_context import (
    CategorizationError,
    LedgerContext,
    build_preview,
    columns,
    digest,
    load_context,
    normalized_parts,
)
from app.finance.categorization_schemas import (
    CategorizationApply,
    CategorizationContext,
    CategorizationPart,
    CategorizationPreview,
    CategorizationPreviewRequest,
)
from app.finance.ledger_validation import _validate_posting_sum
from app.finance.models import (
    FinanceCommandReceipt,
    FinancialTransaction,
    Posting,
    TransactionCategorizationState,
)
from app.finance.rule_models import TransactionCategorizationOrigin

ACTION = "apply_expense_categorization"


async def _record_human_assignment(
    db: AsyncSession,
    ctx: LedgerContext,
    *,
    before: CategorizationContext,
    parts: list[CategorizationPart],
    origin: Literal["manual", "approved_llm"],
    proposal_id: uuid.UUID | None = None,
    approval_receipt_id: uuid.UUID | None = None,
    approval_snapshot_sha256: str | None = None,
) -> None:
    """Private metadata writer; the calling human command proves authority and locks."""
    if ctx.state is None:
        ctx.state = TransactionCategorizationState(
            transaction_id=ctx.txn.id,
            user_id=ctx.txn.user_id,
            version=1,
            source="manual",
            before_snapshot_sha256=before.context_snapshot,
            after_snapshot_sha256="0" * 64,
        )
        db.add(ctx.state)
    else:
        ctx.state.version += 1
        ctx.state.before_snapshot_sha256 = before.context_snapshot
    if ctx.origin is None:
        ctx.origin = TransactionCategorizationOrigin(
            transaction_id=ctx.txn.id,
            user_id=ctx.txn.user_id,
            origin=origin,
            version=1,
            assignment_sha256=digest({"parts": normalized_parts(parts)}),
        )
        db.add(ctx.origin)
    else:
        ctx.origin.version += 1
    ctx.origin.origin = origin
    ctx.origin.rule_id = ctx.origin.rule_version = None
    ctx.origin.proposal_item_id = proposal_id
    ctx.origin.approval_receipt_id = approval_receipt_id
    ctx.origin.approval_snapshot_sha256 = approval_snapshot_sha256
    ctx.origin.assignment_sha256 = digest({"parts": normalized_parts(parts)})
    if origin == "manual":
        ctx.origin_grant = None
    ctx.txn.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(ctx.txn, attribute_names=["updated_at"])
    ctx.state.after_snapshot_sha256 = ctx.snapshot()


async def _write_category_parts(
    db: AsyncSession, ctx: LedgerContext, parts: list[CategorizationPart]
) -> None:
    """Private ledger writer. Caller must validate authority and hold context locks."""
    account = next(p for p in ctx.txn.postings if p.account_id)
    account_before = columns(account)
    available = sorted([p for p in ctx.txn.postings if p.category_id], key=lambda p: str(p.id))
    budget_impact = available[0].is_budget_impact
    assigned: dict[uuid.UUID, Posting] = {}
    for part in parts:
        match = next((p for p in available if p.category_id == part.category_id), None)
        if match:
            assigned[part.category_id] = match
            available.remove(match)
    for part in sorted(parts, key=lambda p: str(p.category_id)):
        posting = assigned.get(part.category_id)
        if posting is None:
            if available:
                posting = available.pop(0)
            else:
                posting = Posting(
                    transaction_id=ctx.txn.id,
                    source_currency="PLN",
                    fx_rate=1,
                    fx_rate_source="manual",
                    direction="credit",
                    is_budget_impact=budget_impact,
                )
                ctx.txn.postings.append(posting)
                db.add(posting)
        posting.category_id = part.category_id
        posting.source_amount = posting.base_amount_pln = part.amount_minor
    for obsolete in available:
        ctx.txn.postings.remove(obsolete)
        await db.delete(obsolete)
    _validate_posting_sum(ctx.txn.postings, "expense")
    await db.flush()
    await db.scalars(
        select(Posting)
        .where(Posting.transaction_id == ctx.txn.id)
        .execution_options(populate_existing=True)
    )
    if columns(account) != account_before:
        raise RuntimeError("Account posting changed during categorization")


async def get_categorization_context(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID
) -> CategorizationContext:
    return (await load_context(db, user_id, transaction_id)).response(allow_imported=True)


async def preview_categorization(
    db: AsyncSession,
    user_id: uuid.UUID,
    transaction_id: uuid.UUID,
    data: CategorizationPreviewRequest,
) -> CategorizationPreview:
    ctx = await load_context(db, user_id, transaction_id, lock=True)
    if (
        ctx.response(allow_imported=True).version != data.expected_version
        or ctx.snapshot() != data.expected_context_snapshot
    ):
        raise CategorizationError(
            "category_snapshot_conflict", "Dane zmieniły się. Zamknij okno i odśwież podział."
        )
    return build_preview(ctx, data.parts, allow_imported=True)


async def apply_categorization(
    db: AsyncSession,
    user_id: uuid.UUID,
    transaction_id: uuid.UUID,
    data: CategorizationApply,
    *,
    idempotency_key: str,
) -> CategorizationContext:
    if (
        await db.scalar(
            select(FinancialTransaction.id).where(
                FinancialTransaction.id == transaction_id, FinancialTransaction.user_id == user_id
            )
        )
        is None
    ):
        raise LookupError("Transaction not found")
    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtext(f"category-command:{user_id}:{idempotency_key}")
            )
        )
    )
    request_hash = digest(
        {
            "transaction_id": transaction_id,
            **data.model_dump(mode="json"),
            "parts": normalized_parts(data.parts),
        }
    )
    receipt = await db.scalar(
        select(FinanceCommandReceipt).where(
            FinanceCommandReceipt.user_id == user_id,
            FinanceCommandReceipt.action == ACTION,
            FinanceCommandReceipt.key == idempotency_key,
        )
    )
    if receipt:
        if receipt.request_hash != request_hash:
            raise CategorizationError(
                "idempotency_key_reused",
                "Ten klucz zatwierdzenia został już użyty dla innej decyzji.",
            )
        return CategorizationContext.model_validate(receipt.response_json)
    ctx = await load_context(db, user_id, transaction_id, lock=True)
    before = ctx.response(allow_imported=True)
    try:
        preview = build_preview(ctx, data.parts, allow_imported=True)
    except CategorizationError as error:
        if error.code == "invalid_category":
            raise CategorizationError(
                "category_snapshot_conflict",
                "Kategorie zmieniły się. Zamknij okno i sprawdź podział ponownie.",
            ) from error
        raise
    if (
        before.version != data.expected_version
        or preview.preview_snapshot != data.expected_preview_snapshot
    ):
        raise CategorizationError(
            "category_snapshot_conflict", "Dane zmieniły się. Zamknij okno i odśwież podział."
        )
    if not (
        ctx.state
        and normalized_parts(before.parts) == normalized_parts(data.parts)
        and (ctx.origin is None or ctx.origin.origin == "manual")
    ):
        old_postings = [columns(p) for p in ctx.txn.postings]
        await _write_category_parts(db, ctx, data.parts)
        await _record_human_assignment(db, ctx, before=before, parts=data.parts, origin="manual")
        from app.finance.proposal_state import supersede_pending_proposals

        await supersede_pending_proposals(db, user_id, transaction_id)
        assert ctx.state is not None
        await log_event(
            db,
            user_id,
            "financial_transaction",
            str(transaction_id),
            ACTION,
            old_state={
                "postings": old_postings,
                "snapshot": before.context_snapshot,
                "assignment_origin": before.assignment_origin.model_dump(mode="json")
                if before.assignment_origin
                else None,
            },
            new_state={
                "postings": [columns(p) for p in ctx.txn.postings],
                "version": ctx.state.version,
                "source": "manual",
                "snapshot": ctx.state.after_snapshot_sha256,
            },
        )
        await db.flush()
    response = ctx.response(allow_imported=True)
    db.add(
        FinanceCommandReceipt(
            user_id=user_id,
            action=ACTION,
            key=idempotency_key,
            request_hash=request_hash,
            entity_id=transaction_id,
            result_ids=[str(transaction_id)],
            version=response.version,
            response_json=response.model_dump(mode="json"),
        )
    )
    await db.flush()
    return response
