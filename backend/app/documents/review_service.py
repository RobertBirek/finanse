import hashlib
import json
import uuid
from typing import Literal, cast

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.documents.models import Document, DocumentExtractionRevision, DocumentText
from app.documents.review_schemas import ReviewResponse, ReviewSuggestion
from app.documents.schemas import DocumentStatus
from app.finance.bills_schemas import MutationContext
from app.finance.models import FinanceCommandReceipt


class ReviewExtractionError(Exception):
    """A provider response was unavailable or unsuitable for a financial review."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _response(revision: DocumentExtractionRevision) -> ReviewResponse:
    suggestion = ReviewSuggestion.model_validate(
        {
            key: revision.data.get(key)
            for key in ("document_type", "fields", "provenance", "parser_version")
        }
    )
    status = revision.status
    if status not in {"pending", "processing", "ready", "incomplete", "error"}:
        raise ValueError("invalid_review_status")
    return ReviewResponse(
        **suggestion.model_dump(),
        id=revision.id,
        document_id=revision.document_id,
        revision=revision.revision,
        status=cast(Literal["pending", "processing", "ready", "incomplete", "error"], status),
        error_code=revision.error_code,
    )


def _request_hash(document_id: uuid.UUID, refresh: bool) -> str:
    return hashlib.sha256(
        json.dumps({"document_id": str(document_id), "refresh": refresh}, sort_keys=True).encode()
    ).hexdigest()


async def prepare_review(
    db: AsyncSession,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    refresh: bool,
    context: MutationContext,
) -> DocumentExtractionRevision:
    """Create a durable review request. The worker, never a GET, performs extraction."""
    request_hash = _request_hash(document_id, refresh)
    document = (
        await db.execute(
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if document is None:
        raise LookupError("document_not_found")

    receipt = (
        await db.execute(
            select(FinanceCommandReceipt).where(
                FinanceCommandReceipt.user_id == user_id,
                FinanceCommandReceipt.action == "prepare_document_review",
                FinanceCommandReceipt.key == context.idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if receipt is not None:
        if receipt.request_hash != request_hash:
            raise ValueError("idempotency_key_reused")
        revision = await db.get(DocumentExtractionRevision, receipt.entity_id)
        if revision is None:
            raise RuntimeError("review_receipt_missing_revision")
        return revision

    latest = (
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
    if latest is not None and not refresh:
        return latest

    revision_number = 1 if latest is None else latest.revision + 1
    text = (
        await db.execute(select(DocumentText).where(DocumentText.document_id == document_id))
    ).scalar_one_or_none()
    revision = DocumentExtractionRevision(
        user_id=user_id,
        document_id=document_id,
        revision=revision_number,
        status="pending" if text is not None and text.extracted_text.strip() else "incomplete",
        data={
            "document_type": "other",
            "fields": {},
            "provenance": {},
            "parser_version": None,
        },
        field_provenance={},
        error_code=None
        if text is not None and text.extracted_text.strip()
        else "ocr_text_unavailable",
    )
    db.add(revision)
    await db.flush()
    snapshot = _response(revision).model_dump(mode="json")
    db.add(
        FinanceCommandReceipt(
            user_id=user_id,
            action="prepare_document_review",
            key=context.idempotency_key,
            request_hash=request_hash,
            entity_id=revision.id,
            result_ids=[str(revision.id)],
            version=revision.revision,
            response_json=snapshot,
        )
    )
    if context.performed_by != "system":
        await log_event(
            db,
            user_id,
            "document_extraction_revision",
            str(revision.id),
            "prepare",
            new_state={"document_id": str(document_id), "revision": revision.revision},
            performed_by=context.performed_by,
        )
    return revision


async def get_review(
    db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID
) -> ReviewResponse | None:
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
    return _response(revision) if revision is not None else None


async def process_review_revision(
    db: AsyncSession, revision_id: uuid.UUID
) -> DocumentExtractionRevision | None:
    """Worker-only extraction with a row lock and no OCR or ledger side effects."""
    revision = (
        await db.execute(
            select(DocumentExtractionRevision)
            .where(DocumentExtractionRevision.id == revision_id)
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()
    if revision is None or revision.status != "pending":
        return revision
    revision.status = "processing"
    text = (
        await db.execute(
            select(DocumentText).where(DocumentText.document_id == revision.document_id)
        )
    ).scalar_one_or_none()
    if text is None or not text.extracted_text.strip():
        revision.status, revision.error_code = "incomplete", "ocr_text_unavailable"
        return revision
    try:
        parsed = await extract_review_data(text.extracted_text)
    except ReviewExtractionError as error:
        revision.status, revision.error_code = "incomplete", error.code
        return revision
    except ValidationError:
        revision.status, revision.error_code = "incomplete", "invalid_model_output"
        return revision
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
        revision.status, revision.error_code = "error", "financial_extraction_failed"
        return revision

    data = parsed.model_dump(mode="json")
    if parsed.fields.total is not None and parsed.fields.currency is not None:
        data["total_minor"] = int(
            parsed.fields.total.replace(".", "").ljust(
                len(parsed.fields.total.split(".")[0]) + 2, "0"
            )
        )
    revision.data = data
    revision.field_provenance = parsed.provenance
    revision.parser_version = parsed.parser_version
    revision.status = "ready"
    revision.error_code = None
    return revision


async def request_ocr_retry(
    db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID, *, context: MutationContext
) -> tuple[Document, dict[str, object]]:
    """Explicitly requeue OCR; list and review reads never retry a document."""
    document = (
        await db.execute(
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if document is None:
        raise LookupError("document_not_found")
    request_hash = hashlib.sha256(
        json.dumps({"document_id": str(document_id)}, sort_keys=True).encode()
    ).hexdigest()
    receipt = (
        await db.execute(
            select(FinanceCommandReceipt).where(
                FinanceCommandReceipt.user_id == user_id,
                FinanceCommandReceipt.action == "retry_document_ocr",
                FinanceCommandReceipt.key == context.idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if receipt is not None:
        if receipt.request_hash != request_hash:
            raise ValueError("idempotency_key_reused")
        return document, receipt.response_json
    document.status = DocumentStatus.PENDING
    document.attempt_count = 0
    document.next_attempt_at = None
    document.last_error_code = None
    await log_event(
        db, user_id, "document", str(document_id), "retry_ocr", performed_by=context.performed_by
    )
    response_json: dict[str, object] = {"id": str(document.id), "status": "pending"}
    db.add(
        FinanceCommandReceipt(
            user_id=user_id,
            action="retry_document_ocr",
            key=context.idempotency_key,
            request_hash=request_hash,
            entity_id=document.id,
            result_ids=[str(document.id)],
            version=None,
            response_json=response_json,
        )
    )
    return document, response_json


async def pending_review_ids(db: AsyncSession) -> list[uuid.UUID]:
    return list(
        (
            await db.execute(
                select(DocumentExtractionRevision.id).where(
                    DocumentExtractionRevision.status == "pending"
                )
            )
        ).scalars()
    )


async def extract_review_data(text: str) -> ReviewSuggestion:
    from app.documents.extractor import extract_review_data as extract

    return await extract(text)
