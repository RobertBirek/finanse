import uuid
from collections.abc import Sequence

from sqlalchemy import and_, case, func, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import CompoundSelect, Subquery

from app.documents.job_models import DocumentProcessingJob
from app.documents.models import Document, DocumentExtractionRevision, DocumentText
from app.documents.schemas import DocumentWorklistCounts, ReviewSummary


async def get_review_summaries(
    db: AsyncSession, user_id: uuid.UUID, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, ReviewSummary]:
    if not ids:
        return {}
    ranked = _ranked_reviews(user_id, ids)
    rows = await db.execute(
        select(
            ranked,
            DocumentProcessingJob.state.label("job_state"),
            DocumentProcessingJob.id.label("job_id"),
        )
        .outerjoin(DocumentProcessingJob, _review_job_join(ranked, user_id))
        .where(ranked.c.rank == 1)
    )
    return {
        row.document_id: ReviewSummary(
            revision_id=row.revision_id,
            revision=row.revision,
            input_method=row.input_method,
            status=row.status,
            error_code=row.error_code,
            warnings=tuple(row.warnings or ()),
            job_state=row.job_state,
            job_id=row.job_id,
        )
        for row in rows
    }


def _ranked_reviews(user_id: uuid.UUID, ids: Sequence[uuid.UUID] | None = None) -> Subquery:
    query = select(
        DocumentExtractionRevision.id.label("revision_id"),
        DocumentExtractionRevision.document_id,
        DocumentExtractionRevision.revision,
        DocumentExtractionRevision.input_method,
        DocumentExtractionRevision.status,
        DocumentExtractionRevision.error_code,
        DocumentExtractionRevision.warnings,
        DocumentExtractionRevision.data["document_type"].as_string().label("document_type"),
        func.row_number()
        .over(
            partition_by=DocumentExtractionRevision.document_id,
            order_by=DocumentExtractionRevision.revision.desc(),
        )
        .label("rank"),
    ).where(
        DocumentExtractionRevision.user_id == user_id,
    )
    if ids is not None:
        query = query.where(DocumentExtractionRevision.document_id.in_(ids))
    return query.subquery()


def _review_job_join(ranked: Subquery, user_id: uuid.UUID) -> ColumnElement[bool]:
    return and_(
        DocumentProcessingJob.revision_id == ranked.c.revision_id,
        DocumentProcessingJob.document_id == ranked.c.document_id,
        DocumentProcessingJob.user_id == user_id,
        DocumentProcessingJob.kind == "vision",
    )


def _ranked_local_ocr(user_id: uuid.UUID, ids: Sequence[uuid.UUID] | None = None) -> Subquery:
    query = select(
        DocumentProcessingJob.id.label("job_id"),
        DocumentProcessingJob.document_id,
        DocumentProcessingJob.state,
        DocumentProcessingJob.error_code,
        func.row_number()
        .over(
            partition_by=DocumentProcessingJob.document_id,
            order_by=(DocumentProcessingJob.created_at.desc(), DocumentProcessingJob.id.desc()),
        )
        .label("rank"),
    ).where(DocumentProcessingJob.user_id == user_id, DocumentProcessingJob.kind == "local_ocr")
    if ids is not None:
        query = query.where(DocumentProcessingJob.document_id.in_(ids))
    return query.subquery()


async def get_local_ocr_summaries(
    db: AsyncSession, user_id: uuid.UUID, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, tuple[uuid.UUID, str, str | None]]:
    if not ids:
        return {}
    ranked = _ranked_local_ocr(user_id, ids)
    rows = await db.execute(select(ranked).where(ranked.c.rank == 1))
    return {row.document_id: (row.job_id, row.state, row.error_code) for row in rows}


def active_processing_document_ids(user_id: uuid.UUID) -> CompoundSelect:
    reviews = _ranked_reviews(user_id)
    ocr = _ranked_local_ocr(user_id)
    active = ("pending", "processing")
    return union(
        select(reviews.c.document_id)
        .outerjoin(DocumentProcessingJob, _review_job_join(reviews, user_id))
        .where(
            reviews.c.rank == 1,
            or_(
                DocumentProcessingJob.state.in_(active),
                and_(DocumentProcessingJob.id.is_(None), reviews.c.status.in_(active)),
            ),
        ),
        select(ocr.c.document_id).where(ocr.c.rank == 1, ocr.c.state.in_(active)),
    )


def document_worklist(user_id: uuid.UUID) -> Subquery:
    """One owner-scoped classification shared by the counter and list."""
    from app.finance.imports.models import ImportSource
    from app.finance.models import FinancialDocument, FinancialDocumentSource

    reviews = _ranked_reviews(user_id)
    ocr = _ranked_local_ocr(user_id)
    review_status = func.coalesce(reviews.c.status, "")
    review_type = func.coalesce(reviews.c.document_type, "")
    ocr_state = func.coalesce(ocr.c.state, "")
    read_error = or_(
        ocr_state == "failed",
        and_(Document.status == "error", ocr_state != "succeeded"),
        review_status.in_(("incomplete", "error")),
    )
    ready = or_(
        FinancialDocument.review == "draft",
        and_(review_status == "ready", review_type.in_(("invoice", "receipt"))),
        and_(
            review_status == "",
            or_(Document.status == "done", ocr_state == "succeeded"),
            select(DocumentText.id).where(DocumentText.document_id == Document.id).exists(),
        ),
    )
    return (
        select(
            Document.id.label("document_id"),
            case((read_error, "errors"), (ready, "review")).label("worklist"),
        )
        .select_from(Document)
        .outerjoin(reviews, and_(reviews.c.document_id == Document.id, reviews.c.rank == 1))
        .outerjoin(ocr, and_(ocr.c.document_id == Document.id, ocr.c.rank == 1))
        .outerjoin(
            FinancialDocumentSource,
            and_(
                FinancialDocumentSource.document_id == Document.id,
                FinancialDocumentSource.user_id == user_id,
            ),
        )
        .outerjoin(
            FinancialDocument,
            and_(
                FinancialDocument.id == FinancialDocumentSource.financial_document_id,
                FinancialDocument.user_id == user_id,
            ),
        )
        .where(
            Document.user_id == user_id,
            Document.archived_at.is_(None),
            Document.processing_method != "bank_import",
            ~select(ImportSource.id)
            .where(ImportSource.user_id == user_id, ImportSource.document_id == Document.id)
            .exists(),
            or_(
                FinancialDocument.id.is_(None),
                and_(FinancialDocument.review == "draft", FinancialDocument.lifecycle == "active"),
            ),
            ~and_(
                Document.processing_method == "legacy_ocr",
                Document.status.in_(("pending", "processing")),
            ),
            Document.id.not_in(active_processing_document_ids(user_id)),
            review_type.not_in(("statement", "loan_schedule", "unsupported", "multiple")),
        )
        .subquery()
    )


async def get_document_worklist_counts(
    db: AsyncSession, user_id: uuid.UUID
) -> DocumentWorklistCounts:
    lists = document_worklist(user_id)
    counts = (
        await db.execute(
            select(
                func.count().filter(lists.c.worklist == "review").label("review"),
                func.count().filter(lists.c.worklist == "errors").label("errors"),
            )
        )
    ).one()
    return DocumentWorklistCounts(review=counts.review, errors=counts.errors)
