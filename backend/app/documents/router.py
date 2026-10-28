import asyncio
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.documents import service
from app.documents.images import ImageNormalizationError, normalize_image
from app.documents.schemas import (
    DocumentResponse,
    DocumentStatus,
    DocumentTextResponse,
    DocumentUploadResponse,
)
from app.documents.upload_limits import DocumentStorageFullError, StorageQuotaExceededError
from app.documents.validation import DocumentValidationUnavailableError
from app.identity.models import User
from app.identity.router import get_current_user
from app.security.rate_limit import limit_upload

logger = logging.getLogger(__name__)
router = APIRouter()
upload_rate_limit = limit_upload(get_current_user)
ALLOWED_MIME_TYPES = {
    "",
    "application/octet-stream",
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/heic",
    "image/heif",
}
preview_rate_limit = limit_upload(get_current_user)


def _private_headers() -> dict[str, str]:
    return {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[User, Depends(get_current_user)],
    _limit: Annotated[None, Depends(upload_rate_limit)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    declared_mime = file.content_type or ""
    if declared_mime not in ALLOWED_MIME_TYPES:
        return JSONResponse(
            content={
                "detail": f"Unsupported file type: {declared_mime}. Allowed: PDF, JPG, PNG, HEIC."
            },
            status_code=400,
        )
    content = bytearray()
    while chunk := await file.read(64 * 1024):
        content.extend(chunk)
        if len(content) > settings.DOCUMENT_MAX_FILE_BYTES:
            return JSONResponse(
                content={"detail": "File exceeds configured size limit."}, status_code=413
            )
    if not content:
        return JSONResponse(content={"detail": "File is empty"}, status_code=400)

    try:
        doc, is_duplicate = await service.store_document(
            db,
            current_user.id,
            bytes(content),
            file.filename or "untitled",
            declared_mime,
        )
    except StorageQuotaExceededError:
        return JSONResponse(content={"detail": "Document storage quota exceeded"}, status_code=413)
    except DocumentStorageFullError:
        return JSONResponse(content={"detail": "Document storage unavailable"}, status_code=507)
    except service.UnsupportedDocumentFormatError:
        return JSONResponse(
            content={"detail": "File content does not match a supported document type."},
            status_code=400,
        )
    except (OSError, DocumentValidationUnavailableError):
        logger.warning("Document storage failed; original was not overwritten")
        return JSONResponse(
            content={
                "detail": "Nie udało się bezpiecznie zapisać dokumentu. Spróbuj ponownie lub zgłoś problem."
            },
            status_code=503,
        )
    # A durable pending row must be visible before a worker receives its ID.
    await db.commit()
    await db.refresh(doc)
    if doc.status == DocumentStatus.PENDING:
        from app.worker import enqueue_process_document

        try:
            await enqueue_process_document(str(doc.id))
        except (OSError, TimeoutError, RedisError):
            # The periodic dispatcher recovers committed pending rows after outages.
            logger.warning("Document %s awaits queue recovery", doc.id)

    return DocumentUploadResponse(
        document=DocumentResponse.model_validate(doc), is_duplicate=is_duplicate
    )


@router.get("/{document_id}/original")
async def get_document_original(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    doc = await service.get_document(db, current_user.id, document_id)
    if doc is None:
        return JSONResponse(content={"detail": "Document not found"}, status_code=404)
    try:
        content = await asyncio.to_thread(
            service.read_verified_document_content,
            service.UPLOAD_DIR / doc.storage_path,
            doc.sha256_hash,
        )
    except (OSError, service.DocumentIntegrityError):
        return JSONResponse(content={"detail": "Document unavailable"}, status_code=503)
    return Response(
        content=content,
        media_type=doc.mime_type,
        headers={**_private_headers(), "Content-Disposition": 'attachment; filename="document"'},
    )


@router.get("/{document_id}/preview")
async def get_document_preview(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    _limit: Annotated[None, Depends(preview_rate_limit)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    doc = await service.get_document(db, current_user.id, document_id)
    if doc is None:
        return JSONResponse(content={"detail": "Document not found"}, status_code=404)
    try:
        content = await asyncio.to_thread(
            service.read_verified_document_content,
            service.UPLOAD_DIR / doc.storage_path,
            doc.sha256_hash,
        )
        if doc.mime_type == "application/pdf":
            return Response(
                content=content, media_type="application/pdf", headers=_private_headers()
            )
        preview = await normalize_image(content, doc.mime_type, thumbnail=True)
    except (OSError, service.DocumentIntegrityError, ImageNormalizationError):
        return JSONResponse(content={"detail": "Document preview unavailable"}, status_code=503)
    return Response(content=preview, media_type="image/jpeg", headers=_private_headers())


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: Annotated[str | None, Query(pattern=r"^(pending|processing|done|error)$")] = None,
):
    docs = await service.get_documents(
        db, current_user.id, limit=limit, offset=offset, status=status
    )
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    doc = await service.get_document(db, current_user.id, document_id)
    if doc is None:
        return JSONResponse(content={"detail": "Document not found"}, status_code=404)
    return DocumentResponse.model_validate(doc)


@router.get("/{document_id}/text", response_model=DocumentTextResponse)
async def get_document_text(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    doc = await service.get_document(db, current_user.id, document_id)
    if doc is None:
        return JSONResponse(content={"detail": "Document not found"}, status_code=404)
    text = await service.get_document_text(db, document_id)
    if text is None:
        return JSONResponse(content={"detail": "Text not yet extracted"}, status_code=404)
    return DocumentTextResponse.model_validate(text)


@router.delete("/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    deleted = await service.delete_document(db, current_user.id, document_id)
    if not deleted:
        return JSONResponse(content={"detail": "Document not found"}, status_code=404)
    return {"message": "Document deleted"}
