import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.documents.receipt_read_schemas import (
    ReceiptReadCancel,
    ReceiptReadContext,
    ReceiptReadExportPreview,
    ReceiptReadJobPage,
    ReceiptReadJobView,
    ReceiptReadPreviewRequest,
    ReceiptReadResultView,
    ReceiptReadStart,
)
from app.finance.categorization_context import CategorizationError
from app.finance.categorization_router import Database, Owner, _error
from app.finance.receipt_read_service import (
    cancel_receipt_read,
    get_receipt_read_context,
    get_receipt_read_job,
    get_receipt_read_result,
    list_receipt_reads,
    preview_receipt_read_export,
    start_receipt_read,
)
from app.finance.rule_router import Key

router = APIRouter()
Cursor = Annotated[str | None, Query(max_length=1024)]


from app.documents.receipt_read_schemas import (
    ReceiptReadImport,
    ReceiptReadImportPreview,
    ReceiptReadImportPreviewRequest,
)
from app.finance.receipt_read_import import import_receipt_read, preview_receipt_read_import
from app.finance.receipt_schemas import ReceiptItemsContext


@router.post("/bills/{bill_id}/items/read-import-preview", response_model=ReceiptReadImportPreview)
async def read_import_preview(
    bill_id: uuid.UUID, data: ReceiptReadImportPreviewRequest, current_user: Owner, db: Database
) -> ReceiptReadImportPreview | JSONResponse:
    try:
        return await preview_receipt_read_import(db, current_user.id, bill_id, data)
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.post("/bills/{bill_id}/items/read-import", response_model=ReceiptItemsContext)
async def read_import(
    bill_id: uuid.UUID,
    data: ReceiptReadImport,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
) -> ReceiptItemsContext | JSONResponse:
    try:
        result = await import_receipt_read(
            db, current_user.id, bill_id, data, idempotency_key=idempotency_key
        )
        await db.commit()
        return result
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.get("/bills/{bill_id}/items/reads/context", response_model=ReceiptReadContext)
async def read_context(
    bill_id: uuid.UUID, current_user: Owner, db: Database, source_cursor: Cursor = None
) -> ReceiptReadContext | JSONResponse:
    try:
        return await get_receipt_read_context(
            db, current_user.id, bill_id, source_cursor=source_cursor
        )
    except (LookupError, CategorizationError) as error:
        return _error(error)


@router.get("/bills/{bill_id}/items/reads", response_model=ReceiptReadJobPage)
async def read_history(
    bill_id: uuid.UUID, current_user: Owner, db: Database, cursor: Cursor = None
) -> ReceiptReadJobPage | JSONResponse:
    try:
        return await list_receipt_reads(db, current_user.id, bill_id, cursor=cursor)
    except (LookupError, CategorizationError) as error:
        return _error(error)


@router.get("/bills/{bill_id}/items/reads/{job_id}", response_model=ReceiptReadJobView)
async def read_job(
    bill_id: uuid.UUID, job_id: uuid.UUID, current_user: Owner, db: Database
) -> ReceiptReadJobView | JSONResponse:
    try:
        return await get_receipt_read_job(db, current_user.id, bill_id, job_id)
    except (LookupError, CategorizationError) as error:
        return _error(error)


@router.get("/bills/{bill_id}/items/reads/{job_id}/result", response_model=ReceiptReadResultView)
async def read_result(
    bill_id: uuid.UUID, job_id: uuid.UUID, current_user: Owner, db: Database
) -> ReceiptReadResultView | JSONResponse:
    try:
        return await get_receipt_read_result(db, current_user.id, bill_id, job_id)
    except (LookupError, CategorizationError) as error:
        return _error(error)


@router.post("/bills/{bill_id}/items/read-export-preview", response_model=ReceiptReadExportPreview)
async def read_export_preview(
    bill_id: uuid.UUID, data: ReceiptReadPreviewRequest, current_user: Owner, db: Database
) -> ReceiptReadExportPreview | JSONResponse:
    try:
        return await preview_receipt_read_export(db, current_user.id, bill_id, data)
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.post("/bills/{bill_id}/items/read-start", response_model=ReceiptReadJobView)
async def read_start(
    bill_id: uuid.UUID,
    data: ReceiptReadStart,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
) -> ReceiptReadJobView | JSONResponse:
    try:
        result = await start_receipt_read(
            db, current_user.id, bill_id, data, idempotency_key=idempotency_key
        )
        await db.commit()
        return result
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.post("/bills/{bill_id}/items/reads/{job_id}/cancel", response_model=ReceiptReadJobView)
async def read_cancel(
    bill_id: uuid.UUID,
    job_id: uuid.UUID,
    data: ReceiptReadCancel,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
) -> ReceiptReadJobView | JSONResponse:
    try:
        result = await cancel_receipt_read(
            db, current_user.id, bill_id, job_id, data, idempotency_key=idempotency_key
        )
        await db.commit()
        return result
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)
