import asyncio
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.documents import service
from app.documents.images import ImageNormalizationError, normalize_image
from app.documents.job_models import DocumentProcessingJob, DocumentVisionPolicy
from app.documents.lifecycle import DocumentLifecycleError, set_document_archived
from app.documents.schemas import (
    DocumentResponse,
    DocumentStatus,
    DocumentTextResponse,
    DocumentUploadCapabilities,
    DocumentUploadResponse,
)
from app.documents.upload_limits import DocumentStorageFullError, StorageQuotaExceededError
from app.documents.validation import DocumentValidationUnavailableError
from app.documents.vision_config import get_vision_config
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
_DIAGNOSTIC_MIME_ALIASES = {"image/heic": "image/heif"}
_DIAGNOSTIC_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/heif"}
_DIAGNOSTIC_REJECTION_CODES = {
    "document_mime_unsupported",
    "document_empty",
    "document_validation_failed",
    "document_mime_mismatch",
}
preview_rate_limit = limit_upload(get_current_user)


def _private_headers() -> dict[str, str]:
    return {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def _diagnostic_mime(mime: str | None) -> str:
    if not mime:
        return "unknown"
    normalized = _DIAGNOSTIC_MIME_ALIASES.get(mime, mime)
    if normalized in _DIAGNOSTIC_MIME_TYPES | {"application/octet-stream"}:
        return normalized
    return "other"


def _document_rejection(
    code: str,
    declared_mime: str | None,
    detected_mime: str | None,
    content_bytes: int,
) -> JSONResponse:
    safe_code = code if code in _DIAGNOSTIC_REJECTION_CODES else "document_validation_failed"
    logger.warning(
        "Document upload rejected code=%s declared_mime=%s detected_mime=%s bytes=%s",
        safe_code,
        _diagnostic_mime(declared_mime),
        _diagnostic_mime(detected_mime),
        content_bytes,
    )
    return JSONResponse(
        content={
            "detail": "File content does not match a supported document type.",
            "code": safe_code,
        },
        status_code=400,
    )


@router.get("/upload-capabilities", response_model=DocumentUploadCapabilities)
async def upload_capabilities(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    del current_user
    config = get_vision_config(settings)
    policy = await db.get(DocumentVisionPolicy, 1)
    automatic = bool(
        settings.DOCUMENT_VISION_ENABLED
        and config
        and policy
        and policy.enabled
        and policy.configuration_fingerprint == config.configuration_fingerprint
    )
    provider_label = config.provider if automatic and config is not None else None
    return DocumentUploadCapabilities(
        max_file_bytes=settings.DOCUMENT_MAX_FILE_BYTES,
        accepted_mime_types=sorted(mime for mime in ALLOWED_MIME_TYPES if mime),
        automatic_image_vision=automatic,
        vision_provider_label=provider_label,
        vision_notice="Image reading is unavailable until enabled by an operator."
        if not automatic
        else None,
    )


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[User, Depends(get_current_user)],
    _limit: Annotated[None, Depends(upload_rate_limit)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    declared_mime = file.content_type or ""
    if declared_mime not in ALLOWED_MIME_TYPES:
        return _document_rejection("document_mime_unsupported", declared_mime, None, 0)
    content = bytearray()
    while chunk := await file.read(64 * 1024):
        content.extend(chunk)
        if len(content) > settings.DOCUMENT_MAX_FILE_BYTES:
            return JSONResponse(
                content={"detail": "File exceeds configured size limit."}, status_code=413
            )
    if not content:
        return _document_rejection("document_empty", declared_mime, None, 0)

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
    except service.UnsupportedDocumentFormatError as error:
        return _document_rejection(
            error.code,
            declared_mime,
            error.detected_mime,
            len(content),
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
        from app.worker import enqueue_process_document, enqueue_process_document_job

        try:
            if doc.processing_method == "vision":
                job_id = await db.scalar(
                    select(DocumentProcessingJob.id).where(
                        DocumentProcessingJob.document_id == doc.id,
                        DocumentProcessingJob.kind == "vision",
                    )
                )
                if job_id is not None:
                    await enqueue_process_document_job(str(job_id))
            else:
                await enqueue_process_document(str(doc.id))
        except (OSError, TimeoutError, RedisError):
            # The periodic dispatcher recovers committed pending rows after outages.
            logger.warning("Document %s awaits queue recovery", doc.id)

    return DocumentUploadResponse(
        document=(await service.document_responses(db, current_user.id, [doc]))[0],
        is_duplicate=is_duplicate,
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


@router.get("/active", response_model=list[DocumentResponse])
async def active_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DocumentResponse]:
    documents = await service.get_active_documents(db, current_user.id, limit, offset)
    return await service.document_responses(db, current_user.id, documents)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: Annotated[str | None, Query(pattern=r"^(pending|processing|done|error)$")] = None,
    archived: bool = False,
):
    docs = await service.get_documents(
        db, current_user.id, limit=limit, offset=offset, status=status, archived=archived
    )
    return await service.document_responses(db, current_user.id, docs)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    doc = await service.get_document(db, current_user.id, document_id)
    if doc is None:
        return JSONResponse(content={"detail": "Document not found"}, status_code=404)
    return (await service.document_responses(db, current_user.id, [doc]))[0]


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
    try:
        deleted = await service.delete_document(db, current_user.id, document_id)
    except DocumentLifecycleError as error:
        return JSONResponse(content={"detail": error.code, "code": error.code}, status_code=409)

    if not deleted:
        return JSONResponse(content={"detail": "Document not found"}, status_code=404)
    return {"message": "Document archived"}


async def _set_archive(
    db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID, *, archived: bool
) -> DocumentResponse | JSONResponse:
    try:
        document = await set_document_archived(db, user_id, document_id, archived=archived)
    except LookupError:
        return JSONResponse(
            content={"detail": "Document not found", "code": "document_not_found"}, status_code=404
        )
    except DocumentLifecycleError as error:
        return JSONResponse(content={"detail": error.code, "code": error.code}, status_code=409)
    # The lifecycle flush expires server-generated updated_at; load it before DTO validation.
    await db.refresh(document)
    return (await service.document_responses(db, user_id, [document]))[0]


@router.post("/{document_id}/archive", response_model=DocumentResponse)
async def archive_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentResponse | JSONResponse:
    return await _set_archive(db, current_user.id, document_id, archived=True)


@router.post("/{document_id}/restore", response_model=DocumentResponse)
async def restore_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentResponse | JSONResponse:
    return await _set_archive(db, current_user.id, document_id, archived=False)
