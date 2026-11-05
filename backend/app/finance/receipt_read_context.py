"""Source-first permission boundary; callers must never request Document after bill locks."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document
from app.finance.categorization_context import CategorizationError
from app.finance.models import FinancialDocument, FinancialDocumentSource
from app.finance.receipt_context import (
    ReceiptDomainContext,
    load_receipt_context,
    receipt_blocked_reason,
    receipt_header_sha256,
)

READ_IMAGE_MIMES = frozenset({"image/jpeg", "image/png", "image/heif"})


@dataclass
class ReceiptReadSource:
    document: Document
    bill: FinancialDocument
    items: ReceiptDomainContext
    link: FinancialDocumentSource
    header_sha256: str


async def owned_receipt_read_document(
    db: AsyncSession, owner: uuid.UUID, document_id: uuid.UUID, *, lock: bool
) -> Document:
    q = (
        select(Document)
        .where(Document.id == document_id, Document.user_id == owner)
        .execution_options(populate_existing=True)
    )
    document = await db.scalar(q.with_for_update() if lock else q)
    if not document:
        raise LookupError("Źródło nie istnieje.")
    return document


async def load_receipt_read_source(
    db: AsyncSession, owner: uuid.UUID, bill_id: uuid.UUID, document: Document, *, lock: bool
) -> ReceiptReadSource:
    ctx = await load_receipt_context(db, owner, bill_id, lock=lock)
    if receipt_blocked_reason(ctx.bill):
        raise CategorizationError(
            "receipt_not_editable", "Potrzebny aktywny zatwierdzony paragon PLN."
        )
    if document.user_id != owner:
        raise LookupError("Źródło nie istnieje.")
    if document.archived_at or document.mime_type not in READ_IMAGE_MIMES:
        raise CategorizationError(
            "source_not_readable", "Wybierz aktywny obraz JPEG, PNG lub HEIF."
        )
    link = await db.scalar(
        select(FinancialDocumentSource)
        .where(
            FinancialDocumentSource.user_id == owner,
            FinancialDocumentSource.financial_document_id == bill_id,
            FinancialDocumentSource.document_id == document.id,
        )
        .execution_options(populate_existing=True)
    )
    if link is None:
        raise LookupError("Źródło nie jest dołączone do tego paragonu.")
    return ReceiptReadSource(document, ctx.bill, ctx, link, receipt_header_sha256(ctx.bill))
