import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.job_models import DocumentProcessingJob
from app.documents.models import DocumentExtractionRevision
from app.documents.schemas import ReviewSummary


async def get_review_summaries(
    db: AsyncSession, user_id: uuid.UUID, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, ReviewSummary]:
    if not ids:
        return {}
    ranked = (
        select(
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
        )
        .where(
            DocumentExtractionRevision.user_id == user_id,
            DocumentExtractionRevision.document_id.in_(ids),
        )
        .subquery()
    )
    rows = await db.execute(
        select(ranked, DocumentProcessingJob.state.label("job_state"))
        .outerjoin(DocumentProcessingJob, DocumentProcessingJob.revision_id == ranked.c.revision_id)
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
        )
        for row in rows
    }
