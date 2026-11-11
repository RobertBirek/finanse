"""Authenticated import staging and explicit financial commands, never client postings."""

import hashlib
import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.documents.import_storage import ImportStorageError, store_import_document
from app.documents.upload_limits import DocumentStorageFullError, StorageQuotaExceededError
from app.finance.credit_cards import CardConflict
from app.finance.document_guards import lock_document_mutations
from app.finance.imports.commands import get_command_result, run_preparation_command
from app.finance.imports.commit import commit_import
from app.finance.imports.contracts import ImportKind
from app.finance.imports.decisions import save_decisions
from app.finance.imports.errors import ImportError
from app.finance.imports.jobs import request_prepare
from app.finance.imports.matching import get_candidates
from app.finance.imports.models import ImportBatch, ImportRow, ImportSource
from app.finance.imports.preview import prepare_preview
from app.finance.imports.queries import get_batch, list_rows
from app.finance.imports.schemas import (
    BatchDTO,
    CommitRequest,
    CommitResult,
    DecisionUpdate,
    PreviewRequest,
    SourceUploadResult,
)
from app.finance.imports.service import create_batch
from app.finance.imports.storage import attach_source
from app.finance.loan_schedule_router import import_routes as schedule_import_routes
from app.identity.models import User
from app.identity.router import get_current_user

Database = Annotated[AsyncSession, Depends(get_db)]
Owner = Annotated[User, Depends(get_current_user)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]
router = APIRouter(prefix="/imports")
router.include_router(schedule_import_routes)


class BatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: ImportKind


class ExistingSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: uuid.UUID


class PublicPreview(BaseModel):
    id: uuid.UUID
    batch_id: uuid.UUID
    version: int
    request_hash: str
    groups: list[dict[str, Any]]
    quotes: list[dict[str, Any]]
    new_transaction_count: int
    linked_count: int
    unresolved_count: int
    warnings: list[str]


async def _handle(operation: Awaitable[Any]) -> Any:
    try:
        return await operation
    except ImportError as error:
        return JSONResponse(
            {"code": error.code, "detail": str(error)}, status_code=error.http_status
        )
    except ImportStorageError as error:
        return JSONResponse(
            {"code": error.code, "detail": "Nie udało się przyjąć źródła."},
            status_code=error.http_status,
        )
    except (StorageQuotaExceededError, DocumentStorageFullError):
        return JSONResponse(
            {"code": "source_storage_full", "detail": "Brak miejsca na źródło."}, status_code=413
        )
    except CardConflict as error:
        return JSONResponse(
            {"code": "card_statement_conflict", "detail": str(error)}, status_code=409
        )
    except ValueError as error:
        return JSONResponse(
            {"code": "import_validation_failed", "detail": str(error)}, status_code=422
        )


async def _batch(db: AsyncSession, owner: uuid.UUID, batch_id: uuid.UUID) -> BatchDTO:
    value = await get_batch(db, owner, batch_id)
    if value is None:
        raise ImportError("import_not_found", "Nie znaleziono importu.", 404)
    return value


@router.post("", response_model=BatchDTO, status_code=201)
async def create(data: BatchCreate, current_user: Owner, db: Database, idempotency_key: Key) -> Any:
    return await _handle(
        run_preparation_command(
            db,
            current_user.id,
            action="bank_import.create",
            key=idempotency_key,
            batch_id=None,
            payload=data.model_dump(mode="json"),
            operation=lambda: create_batch(db, current_user.id, data.kind),
        )
    )


@router.get("", response_model=list[BatchDTO])
async def listing(
    current_user: Owner,
    db: Database,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[BatchDTO]:
    ids = (
        await db.scalars(
            select(ImportBatch.id)
            .where(ImportBatch.user_id == current_user.id)
            .order_by(ImportBatch.created_at.desc(), ImportBatch.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [await _batch(db, current_user.id, value) for value in ids]


@router.get("/{batch_id}", response_model=BatchDTO)
async def detail(batch_id: uuid.UUID, current_user: Owner, db: Database) -> Any:
    return await _handle(_batch(db, current_user.id, batch_id))


@router.post("/{batch_id}/sources", response_model=SourceUploadResult, status_code=201)
async def upload(
    batch_id: uuid.UUID, file: UploadFile, current_user: Owner, db: Database, idempotency_key: Key
) -> Any:
    async def process() -> Any:
        batch = await _batch(db, current_user.id, batch_id)
        if batch.archived_at is not None:
            raise ImportError("import_archived", "Import jest zarchiwizowany.")
        try:
            content = await file.read(settings.DOCUMENT_MAX_FILE_BYTES + 1)
        finally:
            await file.close()
        if len(content) > settings.DOCUMENT_MAX_FILE_BYTES:
            raise ImportError("source_size_limit", "Plik przekracza limit rozmiaru.", 413)

        async def attach() -> SourceUploadResult:
            document, _duplicate = await store_import_document(
                db, current_user.id, filename=file.filename or "", content=content
            )
            return await attach_source(db, current_user.id, batch_id, document.id)

        return await run_preparation_command(
            db,
            current_user.id,
            action="bank_import.attach",
            key=idempotency_key,
            batch_id=batch_id,
            payload={"sha256": hashlib.sha256(content).hexdigest(), "filename": file.filename},
            operation=attach,
        )

    return await _handle(process())


@router.post("/{batch_id}/sources/existing", response_model=SourceUploadResult, status_code=201)
async def existing(
    batch_id: uuid.UUID,
    data: ExistingSource,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
) -> Any:
    return await _handle(
        run_preparation_command(
            db,
            current_user.id,
            action="bank_import.attach",
            key=idempotency_key,
            batch_id=batch_id,
            payload=data.model_dump(mode="json"),
            operation=lambda: attach_source(db, current_user.id, batch_id, data.document_id),
        )
    )


@router.post("/{batch_id}/sources/{source_id}/prepare")
async def prepare(
    batch_id: uuid.UUID,
    source_id: uuid.UUID,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
) -> Any:
    async def process() -> BaseModel:
        async with db.begin_nested():
            source = await db.scalar(
                select(ImportSource.id).where(
                    ImportSource.id == source_id,
                    ImportSource.user_id == current_user.id,
                    ImportSource.batch_id == batch_id,
                )
            )
            if source is None:
                raise ImportError("source_not_found", "Nie znaleziono źródła tego importu.", 404)
            return await request_prepare(db, current_user.id, source_id, idempotency_key)

    return await _handle(process())


@router.get("/{batch_id}/rows")
async def rows(
    batch_id: uuid.UUID,
    current_user: Owner,
    db: Database,
    source_id: uuid.UUID | None = None,
    revision_id: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> Any:
    return await _handle(
        list_rows(
            db,
            current_user.id,
            batch_id,
            source_id=source_id,
            revision_id=revision_id,
            offset=offset,
            limit=limit,
        )
    )


@router.get("/{batch_id}/rows/{row_id}/candidates")
async def candidates(
    batch_id: uuid.UUID, row_id: uuid.UUID, current_user: Owner, db: Database
) -> Any:
    async def process() -> Any:
        if (
            await db.scalar(
                select(ImportRow.id).where(
                    ImportRow.id == row_id,
                    ImportRow.batch_id == batch_id,
                    ImportRow.user_id == current_user.id,
                )
            )
            is None
        ):
            raise ImportError("row_not_found", "Nie znaleziono wiersza tego importu.", 404)
        return await get_candidates(db, current_user.id, row_id)

    return await _handle(process())


@router.put("/{batch_id}/decisions", response_model=BatchDTO)
async def decisions(
    batch_id: uuid.UUID,
    data: DecisionUpdate,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
) -> Any:
    return await _handle(
        run_preparation_command(
            db,
            current_user.id,
            action="bank_import.decisions",
            key=idempotency_key,
            batch_id=batch_id,
            payload=data.model_dump(mode="json"),
            operation=lambda: save_decisions(db, current_user.id, batch_id, data),
        )
    )


@router.post("/{batch_id}/preview", response_model=PublicPreview)
async def preview(
    batch_id: uuid.UUID,
    data: PreviewRequest,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
) -> Any:
    async def process() -> PublicPreview:
        value = await prepare_preview(db, current_user.id, batch_id, data)
        batch = await _batch(db, current_user.id, batch_id)
        plans: Any = value.payload["plans"]
        return PublicPreview(
            id=value.id,
            batch_id=batch_id,
            version=value.version,
            request_hash=value.request_hash,
            groups=plans,
            quotes=[operation["quote"] for plan in plans for operation in plan["operations"]],
            new_transaction_count=value.new_transaction_count,
            linked_count=value.linked_transaction_count,
            unresolved_count=batch.unresolved_count,
            warnings=value.warnings,
        )

    return await _handle(
        run_preparation_command(
            db,
            current_user.id,
            action="bank_import.preview",
            key=idempotency_key,
            batch_id=batch_id,
            payload=data.model_dump(mode="json"),
            operation=process,
        )
    )


@router.post("/{batch_id}/commit", response_model=CommitResult)
async def commit(
    batch_id: uuid.UUID,
    data: CommitRequest,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
) -> Any:
    return await _handle(commit_import(db, current_user.id, batch_id, data, idempotency_key))


@router.get("/{batch_id}/commands/{idempotency_key}")
async def command_result(
    batch_id: uuid.UUID, idempotency_key: str, current_user: Owner, db: Database
) -> Any:
    async def process() -> Any:
        value = await get_command_result(db, current_user.id, batch_id, idempotency_key)
        if value is None:
            raise ImportError("command_not_found", "Brak zapisanego wyniku decyzji.", 404)
        return value

    return await _handle(process())


@router.post("/{batch_id}/archive", response_model=BatchDTO)
async def archive(
    batch_id: uuid.UUID, current_user: Owner, db: Database, idempotency_key: Key
) -> Any:
    async def process() -> BatchDTO:
        await lock_document_mutations(db, current_user.id)
        batch = await db.scalar(
            select(ImportBatch)
            .where(ImportBatch.id == batch_id, ImportBatch.user_id == current_user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if batch is None:
            raise ImportError("import_not_found", "Nie znaleziono importu.", 404)
        if batch.archived_at is None:
            batch.archived_at = datetime.now(UTC)
            batch.version += 1
            await db.flush()
        return await _batch(db, current_user.id, batch_id)

    return await _handle(
        run_preparation_command(
            db,
            current_user.id,
            action="bank_import.archive",
            key=idempotency_key,
            batch_id=batch_id,
            payload={},
            operation=process,
        )
    )
