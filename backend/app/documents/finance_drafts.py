"""Durable DB-only registration after recognition; never a payment or ledger command."""

import uuid

from pydantic import ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor.policies import get_policy_engine
from app.documents.finance_draft_models import DocumentFinanceDraftIntent as Intent
from app.documents.models import Document
from app.documents.models import DocumentExtractionRevision as Revision
from app.documents.review_schemas import ReviewSuggestion
from app.documents.vision_schemas import to_minor_units
from app.finance.bills import prepare_bill
from app.finance.bills_schemas import MutationContext
from app.finance.models import FinancialDocument, FinancialDocumentSource


async def create_finance_draft_intent(
    db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID
) -> Intent:
    document = (
        await db.execute(
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if document is None:
        raise LookupError("document_not_found")
    if document.archived_at is not None:
        raise ValueError("document_archived")
    existing = (
        await db.execute(
            select(Intent).where(Intent.document_id == document_id, Intent.user_id == user_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    intent = Intent(user_id=user_id, document_id=document_id, state="pending")
    db.add(intent)
    await db.flush()
    return intent


def review_block_reason(revision: Revision | None) -> str | None:
    if revision is None:
        return "recognition_unavailable"
    if revision.status != "ready" or revision.warnings:
        return "recognition_incomplete"
    try:
        parsed = ReviewSuggestion.model_validate(revision.data)
        if parsed.document_type not in {"invoice", "receipt"}:
            return "unsupported_document"
        fields = parsed.fields
        if not (
            fields.supplier_name
            and fields.supplier_name.strip()
            and fields.description
            and fields.description.strip()
            and fields.total
            and fields.currency
        ):
            return "missing_required_fields"
        to_minor_units(fields.total)
    except (ValidationError, ValueError, TypeError):
        return "invalid_review"
    return None


async def prepare_pending_finance_draft(db: AsyncSession, intent_id: uuid.UUID) -> str:
    candidate = await db.get(Intent, intent_id)
    if candidate is None:
        return "missing"
    # Same global order as upload/manual bill preparation: document, then own intent.
    document = (
        await db.execute(
            select(Document)
            .where(Document.id == candidate.document_id, Document.user_id == candidate.user_id)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if document is None:
        return "not_claimed"
    intent = (
        await db.execute(
            select(Intent)
            .where(Intent.id == intent_id, Intent.user_id == document.user_id)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if intent is None:
        return "not_claimed"
    if intent.state in {"succeeded", "failed"}:
        return intent.state
    if document.archived_at is not None:
        intent.state, intent.error_code = "needs_review", "document_archived"
        return intent.state
    source = (
        await db.execute(
            select(FinancialDocumentSource)
            .join(
                FinancialDocument,
                FinancialDocument.id == FinancialDocumentSource.financial_document_id,
            )
            .where(
                FinancialDocumentSource.document_id == document.id,
                FinancialDocumentSource.user_id == document.user_id,
                FinancialDocument.user_id == document.user_id,
            )
        )
    ).scalar_one_or_none()
    if source is not None:
        intent.bill_id, intent.state, intent.error_code = (
            source.financial_document_id,
            "succeeded",
            None,
        )
        return intent.state
    revision = (
        await db.execute(
            select(Revision)
            .where(Revision.document_id == document.id, Revision.user_id == document.user_id)
            .order_by(Revision.revision.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if (
        document.status in {"pending", "processing"}
        or revision is not None
        and revision.status in {"pending", "processing"}
    ):
        return intent.state
    intent.revision_id = revision.id if revision else None
    reason = review_block_reason(revision)
    if reason:
        intent.state, intent.error_code = "needs_review", reason
        return intent.state
    if get_policy_engine().check_autonomy("prepare_financial_draft", 1) != 1:
        intent.state, intent.error_code = "needs_review", "policy_blocked"
        return intent.state
    try:
        async with db.begin_nested():
            result = await prepare_bill(
                db,
                document.user_id,
                document.id,
                context=MutationContext(
                    idempotency_key=f"auto-finance-draft:{intent.id}", performed_by="system"
                ),
            )
    except (LookupError, ValueError, RuntimeError, SQLAlchemyError):
        intent.state, intent.error_code = "failed", "draft_registration_failed"
        return intent.state
    intent.bill_id, intent.state, intent.error_code = result.id, "succeeded", None
    return intent.state


async def pending_finance_draft_ids(db: AsyncSession, *, limit: int) -> list[uuid.UUID]:
    latest = (
        select(Revision.id)
        .where(Revision.document_id == Intent.document_id, Revision.user_id == Intent.user_id)
        .order_by(Revision.revision.desc())
        .limit(1)
        .correlate(Intent)
        .scalar_subquery()
    )
    query = (
        select(Intent.id)
        .join(Document, and_(Document.id == Intent.document_id, Document.user_id == Intent.user_id))
        .where(
            Document.archived_at.is_(None),
            Document.status.in_(["done", "error"]),
            or_(
                Intent.state == "pending",
                and_(
                    Intent.state == "needs_review",
                    latest.is_not(None),
                    or_(Intent.revision_id.is_(None), Intent.revision_id != latest),
                ),
            ),
        )
        .order_by(Intent.created_at, Intent.id)
        .limit(limit)
    )
    return list((await db.execute(query)).scalars())
