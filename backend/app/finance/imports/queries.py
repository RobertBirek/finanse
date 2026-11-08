"""Read only owner-scoped import state; never infer a ledger mutation."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document
from app.finance.imports.contracts import ScheduleRow, StatementRow
from app.finance.imports.errors import ImportError
from app.finance.imports.models import (
    ImportBatch,
    ImportEvidence,
    ImportRevision,
    ImportRow,
    ImportSource,
)
from app.finance.imports.schemas import BatchDTO, RowDTO, RowPage, SourceDTO


async def get_batch(db: AsyncSession, owner: uuid.UUID, batch_id: uuid.UUID) -> BatchDTO | None:
    batch = await db.scalar(
        select(ImportBatch).where(ImportBatch.user_id == owner, ImportBatch.id == batch_id)
    )
    if batch is None:
        return None
    records = (
        await db.execute(
            select(ImportSource, Document, ImportRevision)
            .join(Document, (Document.id == ImportSource.document_id) & (Document.user_id == owner))
            .outerjoin(ImportRevision, ImportRevision.id == ImportSource.current_revision_id)
            .where(ImportSource.batch_id == batch_id, ImportSource.user_id == owner)
            .order_by(ImportSource.created_at, ImportSource.id)
        )
    ).all()
    sources = []
    for source, document, revision in records:
        sources.append(
            SourceDTO.model_validate(
                {
                    "id": source.id,
                    "batch_id": batch_id,
                    "document_id": document.id,
                    "sha256": document.sha256_hash,
                    "original_name": document.original_name,
                    "bank": source.bank,
                    "layout": source.layout,
                    "parser_version": source.parser_version,
                    "processing_state": source.processing_state,
                    "validation_state": source.validation_state,
                    "current_revision_id": source.current_revision_id,
                    "checks": revision.checks if revision else [],
                    "warnings": revision.warnings if revision else [],
                }
            )
        )
    unresolved = await db.scalar(
        select(func.count())
        .select_from(ImportRow)
        .join(ImportSource, ImportSource.current_revision_id == ImportRow.revision_id)
        .where(
            ImportRow.user_id == owner,
            ImportRow.batch_id == batch_id,
            ~select(ImportEvidence.id).where(ImportEvidence.row_id == ImportRow.id).exists(),
        )
    )
    return BatchDTO.model_validate(
        {
            "id": batch.id,
            "kind": batch.kind,
            "version": batch.version,
            "archived_at": batch.archived_at,
            "commit_state": batch.commit_state,
            "sources": sources,
            "unresolved_count": unresolved or 0,
        }
    )


async def list_rows(
    db: AsyncSession,
    owner: uuid.UUID,
    batch_id: uuid.UUID,
    *,
    source_id: uuid.UUID | None,
    offset: int,
    limit: int,
) -> RowPage:
    if offset < 0 or limit <= 0 or limit > 100:
        raise ImportError("invalid_pagination", "Nieprawidłowy zakres listy.", 422)
    batch = await db.scalar(
        select(ImportBatch.id).where(ImportBatch.id == batch_id, ImportBatch.user_id == owner)
    )
    if batch is None:
        raise ImportError("import_not_found", "Nie znaleziono importu.", 404)
    if (
        source_id is not None
        and await db.scalar(
            select(ImportSource.id).where(
                ImportSource.id == source_id,
                ImportSource.user_id == owner,
                ImportSource.batch_id == batch_id,
            )
        )
        is None
    ):
        raise ImportError("source_not_found", "Nie znaleziono źródła.", 404)
    statement = (
        select(ImportRow)
        .join(ImportSource, ImportSource.current_revision_id == ImportRow.revision_id)
        .where(
            ImportRow.user_id == owner,
            ImportRow.batch_id == batch_id,
        )
    )
    if source_id is not None:
        statement = statement.where(ImportRow.source_id == source_id)
    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    rows = (
        await db.scalars(
            statement.order_by(ImportRow.source_id, ImportRow.ordinal).offset(offset).limit(limit)
        )
    ).all()
    items = []
    for row in rows:
        value = (
            StatementRow.model_validate(row.fields)
            if row.kind == "statement"
            else ScheduleRow.model_validate(row.fields)
        )
        items.append(
            RowDTO.model_validate(
                {
                    "id": row.id,
                    "source_id": row.source_id,
                    "revision_id": row.revision_id,
                    "source_key": row.source_key,
                    "position": value.position,
                    "kind": row.kind,
                    "bank_fields": value if isinstance(value, StatementRow) else None,
                    "schedule_fields": value if isinstance(value, ScheduleRow) else None,
                }
            )
        )
    return RowPage(items=items, total=total, offset=offset, limit=limit)
