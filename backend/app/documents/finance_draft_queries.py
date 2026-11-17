"""Owner-scoped batch projection; reads do not create intents or run recognition."""

import uuid
from collections.abc import Sequence

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.finance_draft_models import DocumentFinanceDraftIntent as Intent
from app.documents.finance_draft_schemas import FinanceDraftSummary
from app.documents.models import Document
from app.finance.models import FinancialDocument as Bill
from app.finance.models import FinancialDocumentSource as Source


async def get_finance_summaries(
    db: AsyncSession, user_id: uuid.UUID, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, FinanceDraftSummary]:
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(
                Document.id.label("document_id"),
                Intent.state,
                Intent.error_code,
                Bill.id.label("bill_id"),
                Bill.review,
                Bill.lifecycle,
            )
            .outerjoin(
                Source,
                and_(Source.document_id == Document.id, Source.user_id == user_id),
            )
            .outerjoin(Bill, and_(Bill.id == Source.financial_document_id, Bill.user_id == user_id))
            .outerjoin(Intent, and_(Intent.document_id == Document.id, Intent.user_id == user_id))
            .where(Document.user_id == user_id, Document.id.in_(ids))
        )
    ).all()
    result = {doc_id: FinanceDraftSummary() for doc_id in ids}
    for row in rows:
        result[row.document_id] = FinanceDraftSummary(
            state=row.state or "not_requested",
            error_code=row.error_code,
            bill_id=row.bill_id,
            review=row.review,
            lifecycle=row.lifecycle,
        )
    return result
