"""Bounded page projection: load ledger evidence once per page, never per item."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.finance.categorization_context import CategorizationError, LedgerContext
from app.finance.models import (
    Account,
    ActualImportMapping,
    Category,
    DocumentPaymentAllocation,
    FinancialTransaction,
    LoanPaymentLink,
    Posting,
    TransactionCategorizationState,
    TransactionDateMetadata,
)
from app.finance.proposal_schemas import ProposalDetail
from app.finance.rule_events import eligible_unclassified
from app.finance.rule_models import TransactionCategorizationOrigin
from app.finance.suggestion_models import CategorizationProposalItem as Item
from app.finance.suggestion_packet import suggestion_taxonomy


async def load_proposal_contexts(
    db: AsyncSession, owner: uuid.UUID, ids: list[uuid.UUID]
) -> dict[uuid.UUID, LedgerContext]:
    if not ids:
        return {}
    txns = (
        await db.scalars(
            select(FinancialTransaction)
            .where(FinancialTransaction.user_id == owner, FinancialTransaction.id.in_(ids))
            .options(selectinload(FinancialTransaction.postings))
            .execution_options(populate_existing=True)
        )
    ).all()
    ids = [txn.id for txn in txns]  # Never read auxiliary evidence of a foreign source.
    categories = {
        c.id: c
        for c in (
            await db.scalars(
                select(Category)
                .where(Category.user_id == owner)
                .execution_options(populate_existing=True)
            )
        ).all()
    }
    accounts = {
        a.id: a
        for a in (
            await db.scalars(
                select(Account)
                .where(
                    Account.id.in_([p.account_id for t in txns for p in t.postings if p.account_id])
                )
                .execution_options(populate_existing=True)
            )
        ).all()
    }
    states = {
        r.transaction_id: r
        for r in (
            await db.scalars(
                select(TransactionCategorizationState)
                .where(TransactionCategorizationState.transaction_id.in_(ids))
                .execution_options(populate_existing=True)
            )
        ).all()
    }
    origins = {
        r.transaction_id: r
        for r in (
            await db.scalars(
                select(TransactionCategorizationOrigin)
                .where(TransactionCategorizationOrigin.transaction_id.in_(ids))
                .execution_options(populate_existing=True)
            )
        ).all()
    }
    dates = {
        r.transaction_id: r
        for r in (
            await db.scalars(
                select(TransactionDateMetadata)
                .where(TransactionDateMetadata.transaction_id.in_(ids))
                .execution_options(populate_existing=True)
            )
        ).all()
    }
    mappings = defaultdict(list)
    for r in (
        await db.scalars(
            select(ActualImportMapping)
            .where(
                ActualImportMapping.entity_type == "transaction",
                ActualImportMapping.entity_id.in_(ids),
            )
            .order_by(ActualImportMapping.id)
        )
    ).all():
        mappings[r.entity_id].append(r)
    loans: dict[uuid.UUID, list[LoanPaymentLink]] = defaultdict(list)
    for loan in (
        await db.scalars(
            select(LoanPaymentLink)
            .where(LoanPaymentLink.transaction_id.in_(ids))
            .order_by(LoanPaymentLink.id)
        )
    ).all():
        loans[loan.transaction_id].append(loan)
    allocations = defaultdict(list)
    for r, txn_id in (
        await db.execute(
            select(DocumentPaymentAllocation, Posting.transaction_id)
            .join(Posting, Posting.id == DocumentPaymentAllocation.posting_id)
            .where(Posting.transaction_id.in_(ids))
            .order_by(DocumentPaymentAllocation.id)
            .execution_options(populate_existing=True)
        )
    ).all():
        allocations[txn_id].append(r)
    return {
        t.id: LedgerContext(
            t,
            states.get(t.id),
            categories,
            next((accounts.get(p.account_id) for p in t.postings if p.account_id), None),
            mappings[t.id],
            loans[t.id],
            allocations[t.id],
            dates.get(t.id),
            origins.get(t.id),
        )
        for t in txns
    }


def proposal_blocked_reason(
    item: Item, ctx: LedgerContext | None, marker: uuid.UUID | None, taxonomy_sha256: str | None
) -> str | None:
    if ctx is None:
        return "source_missing"
    if item.status != "pending":
        return "not_pending"
    if item.expires_at <= datetime.now(UTC):
        return "proposal_expired"
    if (
        not eligible_unclassified(ctx, marker)
        or (ctx.origin and ctx.origin.user_id != item.user_id)
        or ctx.snapshot() != item.source_context_sha256
    ):
        return "source_changed"
    if taxonomy_sha256 is None or taxonomy_sha256 != item.taxonomy_sha256:
        return "taxonomy_changed"
    if item.decision != "existing_category":
        return "manual_category_required"
    if item.target_category_id == marker or item.target_category_id not in ctx.categories:
        return "invalid_target"
    return None


def project_proposal(
    item: Item,
    ctx: LedgerContext | None,
    marker: uuid.UUID | None,
    *,
    taxonomy: tuple[list[dict[str, str]], dict[str, uuid.UUID], str] | None = None,
) -> ProposalDetail:
    if taxonomy is None and ctx and marker:
        try:
            taxonomy = suggestion_taxonomy(ctx.categories, item.user_id, marker)
        except CategorizationError:
            pass
    paths = (
        {
            mapping[key]: row["path"]
            for row in taxonomy[0]
            for key, mapping in [(row["key"], taxonomy[1])]
        }
        if taxonomy
        else {}
    )
    reason = proposal_blocked_reason(item, ctx, marker, taxonomy[2] if taxonomy else None)
    amount = (
        next((p.source_amount for p in ctx.txn.postings if p.account_id), None) if ctx else None
    )
    new = None
    if item.new_category:
        parent_key = item.new_category.get("parent_key")
        parent = item.private_key_map.get(parent_key) if isinstance(parent_key, str) else None
        new = {
            "name": item.new_category["name"],
            "explanation": item.new_category["explanation"],
            "parent_path": paths.get(uuid.UUID(parent)) if parent else None,
        }
    return ProposalDetail(
        id=item.id,
        version=item.version,
        status=item.status,
        transaction_id=ctx.txn.id if ctx else None,
        description=item.generated_description,
        amount_minor=amount,
        decision=item.decision,
        explanation=item.explanation,
        confidence=item.confidence,
        new_category=new,
        current_parts=ctx.response().parts if ctx else [],
        target_path=paths.get(item.target_category_id) if item.target_category_id else None,
        eligible=reason is None,
        blocked_reason=reason,
        expires_at=item.expires_at,
    )
