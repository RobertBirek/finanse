"""Owner-scoped immutable source attachment and verified parser input."""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.documents.import_storage import (
    ImportStorageError,
    read_import_original,
    validate_import_csv,
)
from app.documents.job_models import DocumentProcessingJob
from app.documents.lifecycle import _has_active_work
from app.documents.models import Document
from app.finance.document_guards import lock_document_mutations
from app.finance.imports.contracts import ParserInput
from app.finance.imports.errors import ImportError
from app.finance.imports.models import ImportBatch, ImportSource
from app.finance.imports.pdf_text import configured_pdf_limits, extract_pdf_pages
from app.finance.imports.queries import get_batch
from app.finance.imports.schemas import SourceUploadResult


async def _parser_input(document: Document) -> ParserInput:
    try:
        content = await asyncio.to_thread(read_import_original, document)
        if document.mime_type == "application/pdf":
            pages = await asyncio.to_thread(extract_pdf_pages, content, configured_pdf_limits())
        elif document.mime_type == "text/csv":
            await asyncio.to_thread(validate_import_csv, content)
            pages = None
        else:
            raise ImportError(
                "source_format_unsupported", "Wybierz tekstowy PDF lub obsługiwany CSV.", 422
            )
    except ImportStorageError as error:
        raise ImportError(
            error.code, "Nie udało się zweryfikować oryginału.", error.http_status
        ) from error
    return ParserInput(
        content=content, pages=pages, mime_type=document.mime_type, sha256=document.sha256_hash
    )


async def attach_source(
    db: AsyncSession,
    owner: uuid.UUID,
    batch_id: uuid.UUID,
    document_id: uuid.UUID,
) -> SourceUploadResult:
    initial_batch = await db.scalar(
        select(ImportBatch).where(
            ImportBatch.id == batch_id,
            ImportBatch.user_id == owner,
        )
    )
    if initial_batch is None:
        raise ImportError("import_not_found", "Nie znaleziono importu.", 404)
    initial = await db.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == owner)
    )
    if initial is None:
        raise ImportError("source_not_found", "Nie znaleziono dokumentu.", 404)
    if initial.archived_at is not None or initial_batch.archived_at is not None:
        raise ImportError("source_archived", "Źródło lub import jest zarchiwizowany.")
    if initial.status in {"pending", "processing"}:
        raise ImportError(
            "document_processing_active", "Poczekaj na zakończenie przetwarzania dokumentu."
        )
    await _parser_input(initial)
    expected = (initial.sha256_hash, initial.size_bytes, initial.mime_type, initial.storage_path)
    await lock_document_mutations(db, owner)
    batch = await db.scalar(
        select(ImportBatch)
        .where(
            ImportBatch.id == batch_id,
            ImportBatch.user_id == owner,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if batch is None:
        raise ImportError("import_not_found", "Nie znaleziono importu.", 404)
    if batch.archived_at is not None:
        raise ImportError("import_archived", "Import jest zarchiwizowany.")
    document = await db.scalar(
        select(Document)
        .where(
            Document.id == document_id,
            Document.user_id == owner,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if document is None:
        raise ImportError("source_not_found", "Nie znaleziono dokumentu.", 404)
    if document.archived_at is not None:
        raise ImportError("document_archived", "Najpierw przywróć dokument.")
    if document.status in {"pending", "processing"} or await _has_active_work(db, document):
        raise ImportError(
            "document_processing_active", "Poczekaj na zakończenie przetwarzania dokumentu."
        )
    paused_job = await db.scalar(
        select(DocumentProcessingJob.id)
        .where(
            DocumentProcessingJob.document_id == document_id,
            DocumentProcessingJob.user_id == owner,
            DocumentProcessingJob.state == "paused",
        )
        .limit(1)
    )
    if paused_job:
        raise ImportError(
            "document_processing_active", "Najpierw zakończ wstrzymane przetwarzanie dokumentu."
        )
    if (
        document.sha256_hash,
        document.size_bytes,
        document.mime_type,
        document.storage_path,
    ) != expected:
        raise ImportError("source_version_conflict", "Źródło zmieniło się podczas odczytu.")
    try:
        await asyncio.to_thread(read_import_original, document)
    except ImportStorageError as error:
        raise ImportError(
            error.code, "Nie udało się zweryfikować oryginału.", error.http_status
        ) from error
    existing = await db.scalar(
        select(ImportSource).where(
            ImportSource.user_id == owner,
            ImportSource.document_id == document_id,
            ImportSource.kind == batch.kind,
        )
    )
    if existing is not None:
        result_batch = await get_batch(db, owner, existing.batch_id)
        if result_batch is None:
            raise RuntimeError("Existing source has no owner-scoped batch")
        source = next(item for item in result_batch.sources if item.id == existing.id)
        return SourceUploadResult(
            source=source, is_duplicate=True, existing_batch_id=existing.batch_id
        )
    source_model = ImportSource(
        user_id=owner, batch_id=batch_id, document_id=document_id, kind=batch.kind
    )
    db.add(source_model)
    batch.version += 1
    await db.flush()
    await log_event(
        db,
        owner,
        "bank_import_source",
        str(source_model.id),
        "attach_source",
        new_state={
            "batch_id": str(batch_id),
            "document_id": str(document_id),
            "kind": batch.kind,
            "sha256": document.sha256_hash,
        },
    )
    result_batch = await get_batch(db, owner, batch_id)
    if result_batch is None:
        raise RuntimeError("New source has no owner-scoped batch")
    source = next(item for item in result_batch.sources if item.id == source_model.id)
    return SourceUploadResult(source=source, is_duplicate=False)


async def read_import_input(
    db: AsyncSession, owner: uuid.UUID, source_id: uuid.UUID
) -> ParserInput:
    record = (
        await db.execute(
            select(ImportSource, Document, ImportBatch)
            .join(Document, (Document.id == ImportSource.document_id) & (Document.user_id == owner))
            .join(
                ImportBatch,
                (ImportBatch.id == ImportSource.batch_id) & (ImportBatch.user_id == owner),
            )
            .where(ImportSource.id == source_id, ImportSource.user_id == owner)
        )
    ).one_or_none()
    if record is None:
        raise ImportError("source_not_found", "Nie znaleziono źródła.", 404)
    _source, document, batch = record
    if document.archived_at is not None or batch.archived_at is not None:
        raise ImportError("source_archived", "Źródło lub import jest zarchiwizowany.")
    return await _parser_input(document)
