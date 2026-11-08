"""Owner-scoped, reversible document visibility. Never delete source evidence."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.documents.job_models import DocumentProcessingJob
from app.documents.models import Document, DocumentExtractionRevision
from app.documents.receipt_read_models import ReceiptReadJob
from app.documents.receipt_read_schemas import READ_ACTIVE_STATES


class DocumentLifecycleError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def require_document_unarchived(document: Document) -> None:
    if getattr(document, "archived_at", None) is not None:
        raise DocumentLifecycleError("document_archived")


async def document_has_import_source(db: AsyncSession, document: Document) -> bool:
    from app.finance.imports.models import ImportSource

    return (
        await db.scalar(
            select(ImportSource.id)
            .where(
                ImportSource.document_id == document.id,
                ImportSource.user_id == document.user_id,
            )
            .limit(1)
        )
        is not None
    )


async def require_document_processing_allowed(db: AsyncSession, document: Document) -> None:
    require_document_unarchived(document)
    if document.processing_method == "bank_import" or await document_has_import_source(
        db, document
    ):
        raise DocumentLifecycleError("document_import_source")


async def _has_active_work(db: AsyncSession, document: Document) -> bool:
    if await db.scalar(
        select(ReceiptReadJob.id)
        .where(
            ReceiptReadJob.document_id == document.id,
            ReceiptReadJob.user_id == document.user_id,
            ReceiptReadJob.state.in_(READ_ACTIVE_STATES),
        )
        .limit(1)
    ):
        return True
    if document.processing_method == "legacy_ocr" and document.status in {"pending", "processing"}:
        return True
    active = await db.scalar(
        select(DocumentProcessingJob.id)
        .where(
            DocumentProcessingJob.document_id == document.id,
            DocumentProcessingJob.state.in_(("pending", "processing")),
        )
        .limit(1)
    )
    if active is not None:
        return True
    review = await db.scalar(
        select(DocumentExtractionRevision.id)
        .outerjoin(
            DocumentProcessingJob,
            DocumentProcessingJob.revision_id == DocumentExtractionRevision.id,
        )
        .where(
            DocumentExtractionRevision.document_id == document.id,
            DocumentExtractionRevision.status.in_(("pending", "processing")),
            or_(
                DocumentProcessingJob.id.is_(None),
                DocumentProcessingJob.state.in_(("pending", "processing")),
            ),
        )
        .limit(1)
    )
    return review is not None


async def set_document_archived(
    db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID, *, archived: bool
) -> Document:
    document = (
        await db.execute(
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
            .with_for_update(skip_locked=archived)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if document is None:
        # A running legacy/text worker holds the document until its result commits.
        # Refuse the archive now, rather than silently queueing it behind that work.
        if (
            archived
            and await db.scalar(
                select(Document.id).where(Document.id == document_id, Document.user_id == user_id)
            )
            is not None
        ):
            raise DocumentLifecycleError("document_processing_active")
        raise LookupError("document_not_found")
    if (document.archived_at is not None) == archived:
        return document
    if archived and await document_has_import_source(db, document):
        raise DocumentLifecycleError("document_import_source")
    if archived and await _has_active_work(db, document):
        raise DocumentLifecycleError("document_processing_active")
    old_state = {"archived_at": document.archived_at.isoformat() if document.archived_at else None}
    document.archived_at = datetime.now(UTC) if archived else None
    await log_event(
        db,
        user_id,
        "document",
        str(document_id),
        "archived" if archived else "restored",
        old_state=old_state,
        new_state={
            "archived_at": document.archived_at.isoformat() if document.archived_at else None
        },
    )
    return document
