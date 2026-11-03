import uuid
from collections.abc import Sequence

from sqlalchemy import and_, func, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import CompoundSelect, Subquery

from app.documents.job_models import DocumentProcessingJob
from app.documents.models import DocumentExtractionRevision
from app.documents.schemas import ReviewSummary


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
