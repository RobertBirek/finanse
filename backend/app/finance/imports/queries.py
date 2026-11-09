"""Read only owner-scoped import state; never infer a ledger mutation."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document
from app.finance.imports.contracts import ScheduleRow, StatementRow
from app.finance.imports.errors import ImportError
from app.finance.imports.models import (
    ImportBatch,
    ImportDecision,
    ImportEvidence,
    ImportGroup,
    ImportGroupRow,
    ImportRevision,
    ImportRow,
    ImportSource,
)
from app.finance.imports.schemas import BatchDTO, ReviewGroupDTO, RowDTO, RowPage, SourceDTO


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
    revisions = (
        await db.scalars(
            select(ImportRevision)
            .where(ImportRevision.user_id == owner, ImportRevision.batch_id == batch_id)
            .order_by(ImportRevision.source_id, ImportRevision.number.desc())
        )
    ).all()
    latest: dict[uuid.UUID, ImportRevision] = {}
    for revision_entry in revisions:
        latest.setdefault(revision_entry.source_id, revision_entry)
    sources = []
    for source, document, revision in records:
        candidate = latest.get(source.id)
        if candidate is not None and candidate.id == source.current_revision_id:
            candidate = None
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
                    "candidate_revision_id": candidate.id if candidate else None,
                    "candidate_parser_version": candidate.parser_version if candidate else None,
                    "checks": revision.checks if revision else [],
                    "warnings": list(
                        dict.fromkeys(
                            [
                                *(revision.warnings if revision else []),
                                *(candidate.warnings if candidate else []),
                            ]
                        )
                    ),
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
    groups = (
        await db.execute(
            select(ImportGroup, ImportDecision)
            .outerjoin(
                ImportDecision,
                (ImportDecision.group_id == ImportGroup.id)
                & (ImportDecision.user_id == owner)
                & (ImportDecision.version == ImportGroup.version),
            )
            .where(ImportGroup.user_id == owner, ImportGroup.batch_id == batch_id)
            .order_by(ImportGroup.created_at, ImportGroup.id)
        )
    ).all()
    membership = (
        await db.scalars(
            select(ImportGroupRow)
            .where(ImportGroupRow.user_id == owner, ImportGroupRow.batch_id == batch_id)
            .order_by(ImportGroupRow.row_id)
        )
    ).all()
    grouped_rows: dict[uuid.UUID, list[uuid.UUID]] = {}
    for member in membership:
        grouped_rows.setdefault(member.group_id, []).append(member.row_id)
    group_dtos = [
        ReviewGroupDTO.model_validate(
            {
                "id": group.id,
                "version": group.version,
                "state": group.state,
                "row_ids": grouped_rows.get(group.id, []),
                "decision": decision.data if decision else None,
            }
        )
        for group, decision in groups
    ]
    return BatchDTO.model_validate(
        {
            "id": batch.id,
            "kind": batch.kind,
            "version": batch.version,
            "archived_at": batch.archived_at,
            "commit_state": batch.commit_state,
            "sources": sources,
            "unresolved_count": unresolved or 0,
            "groups": group_dtos,
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
    revision_id: uuid.UUID | None = None,
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
    if revision_id is not None and (
        source_id is None
        or await db.scalar(
            select(ImportRevision.id).where(
                ImportRevision.id == revision_id,
                ImportRevision.user_id == owner,
                ImportRevision.batch_id == batch_id,
                ImportRevision.source_id == source_id,
            )
        )
        is None
    ):
        raise ImportError("revision_not_found", "Nie znaleziono odczytu tego źródła.", 404)
    statement = (
        select(ImportRow)
        .join(
            ImportSource, (ImportSource.id == ImportRow.source_id) & (ImportSource.user_id == owner)
        )
        .where(
            ImportRow.user_id == owner,
            ImportRow.batch_id == batch_id,
        )
    )
    if revision_id is None:
        statement = statement.where(ImportSource.current_revision_id == ImportRow.revision_id)
    else:
        statement = statement.where(ImportRow.revision_id == revision_id)
    if source_id is not None:
        statement = statement.where(ImportRow.source_id == source_id)
    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    rows = (
        await db.scalars(
            statement.order_by(ImportRow.source_id, ImportRow.ordinal).offset(offset).limit(limit)
        )
    ).all()
    items = []
    decisions = (
        await db.execute(
            select(ImportGroupRow.row_id, ImportDecision.data)
            .join(
                ImportGroup,
                (ImportGroup.id == ImportGroupRow.group_id) & (ImportGroup.user_id == owner),
            )
            .join(
                ImportDecision,
                (ImportDecision.group_id == ImportGroup.id)
                & (ImportDecision.user_id == owner)
                & (ImportDecision.version == ImportGroup.version),
            )
            .where(
                ImportGroupRow.user_id == owner,
                ImportGroupRow.batch_id == batch_id,
                ImportGroupRow.row_id.in_([row.id for row in rows]),
            )
        )
    ).all()
    row_decisions = {row_id: data for row_id, data in decisions}
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
                    "decision": row_decisions.get(row.id),
                }
            )
        )
    return RowPage(items=items, total=total, offset=offset, limit=limit)
