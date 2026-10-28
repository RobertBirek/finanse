import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import httpx
from arq import create_pool, cron
from arq.connections import ArqRedis, RedisSettings
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.documents import service
from app.documents.images import normalize_image
from app.documents.models import Document
from app.documents.ocr_client import OCRResponseTooLargeError, post_bounded
from app.documents.retry import is_retryable_ocr_error, retry_delay_seconds
from app.documents.review_service import pending_review_ids, process_review_revision
from app.documents.schemas import DocumentStatus

logger = logging.getLogger(__name__)

REDIS_SETTINGS = RedisSettings.from_dsn(settings.REDIS_URL)
STIRLING_OCR_URL = f"{settings.STIRLING_PDF_URL}/api/v1/misc/ocr-pdf"
STIRLING_IMG_TO_PDF_URL = f"{settings.STIRLING_PDF_URL}/api/v1/convert/img/pdf"
STIRLING_PDF_TO_TEXT_URL = f"{settings.STIRLING_PDF_URL}/api/v1/convert/pdf/text"


async def enqueue_process_document(document_id: str) -> None:
    redis: ArqRedis = await create_pool(REDIS_SETTINGS)
    try:
        await redis.enqueue_job("process_document", document_id, _job_id=f"document:{document_id}")
    finally:
        await redis.aclose()


async def enqueue_prepare_document_review(revision_id: str) -> None:
    redis: ArqRedis = await create_pool(REDIS_SETTINGS)
    try:
        await redis.enqueue_job(
            "prepare_document_review", revision_id, _job_id=f"document-review:{revision_id}"
        )
    finally:
        await redis.aclose()


async def dispatch_pending_documents(ctx) -> None:
    """PostgreSQL pending rows are durable work, Redis is only a delivery mechanism."""
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.DOCUMENT_STALE_PROCESSING_SECONDS)
    async with async_session_factory() as db:
        documents = (
            (
                await db.execute(
                    select(Document)
                    .where(
                        or_(
                            and_(
                                Document.status == DocumentStatus.PENDING,
                                or_(
                                    Document.next_attempt_at.is_(None),
                                    Document.next_attempt_at <= datetime.now(UTC),
                                ),
                            ),
                            and_(
                                Document.status == DocumentStatus.PROCESSING,
                                Document.updated_at < cutoff,
                            ),
                        )
                    )
                    .order_by(Document.created_at)
                    .limit(settings.DOCUMENT_DISPATCH_BATCH_SIZE)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        ids = [document.id for document in documents]
        for document in documents:
            if document.status == DocumentStatus.PROCESSING:
                document.status = DocumentStatus.PENDING
        # Commit recovery before enqueueing. On queue failure pending remains
        # durable; rows held by active workers were skipped, never stolen.
        await db.commit()
    for document_id in ids:
        await ctx["redis"].enqueue_job(
            "process_document", str(document_id), _job_id=f"document:{document_id}"
        )


async def dispatch_pending_document_reviews(ctx) -> None:
    async with async_session_factory() as db:
        revision_ids = await pending_review_ids(db)
    for revision_id in revision_ids:
        await ctx["redis"].enqueue_job(
            "prepare_document_review", str(revision_id), _job_id=f"document-review:{revision_id}"
        )


async def _convert_image_to_pdf(
    client: httpx.AsyncClient, file_path: str, image_content: bytes | None = None
) -> bytes:
    path = Path(file_path)
    content = (
        image_content if image_content is not None else await asyncio.to_thread(path.read_bytes)
    )
    files = {"fileInput": (path.name, content)}
    # Keep text glyphs undistorted; choose landscape A4 for wide images.
    data = {"fitOption": "maintainAspectRatio", "autoRotate": "true"}
    return await post_bounded(
        client, STIRLING_IMG_TO_PDF_URL, files, settings.DOCUMENT_OCR_MAX_BYTES, data
    )


async def _ocr_pdf(
    client: httpx.AsyncClient, file_path: str, pdf_content: bytes | None = None
) -> bytes:
    """Use converted PDF bytes for images without changing their original files."""
    path = Path(file_path)
    content = pdf_content if pdf_content is not None else await asyncio.to_thread(path.read_bytes)
    files = {"fileInput": (path.name, content)}
    data = {"languages": "pol,eng", "ocrType": "skip-text"}
    return await post_bounded(
        client, STIRLING_OCR_URL, files, settings.DOCUMENT_OCR_MAX_BYTES, data
    )


async def _pdf_to_text(client: httpx.AsyncClient, pdf_content: bytes) -> str:
    files = {"fileInput": ("output.pdf", pdf_content, "application/pdf")}
    content = await post_bounded(
        client,
        STIRLING_PDF_TO_TEXT_URL,
        files,
        settings.DOCUMENT_OCR_TEXT_MAX_BYTES,
        {"outputFormat": "txt"},
    )
    text = content.decode("utf-8", errors="replace")
    if len(text.encode("utf-8")) > settings.DOCUMENT_OCR_TEXT_MAX_BYTES:
        raise OCRResponseTooLargeError("OCR text exceeds limit")
    return text


async def _process_content(db: AsyncSession, doc: Document) -> None:
    document_path = service.UPLOAD_DIR / doc.storage_path
    file_path = str(document_path)
    original_content = await asyncio.to_thread(
        service.read_verified_document_content, document_path, doc.sha256_hash
    )
    async with httpx.AsyncClient(timeout=120.0) as client:
        converted = None
        if doc.mime_type.startswith("image/"):
            image_content = original_content
            image_path = file_path
            if doc.mime_type == "image/heif":
                image_content = await normalize_image(original_content, doc.mime_type)
                image_path = "document.jpg"
            converted = await _convert_image_to_pdf(client, image_path, image_content)
        ocr_pdf = await _ocr_pdf(
            client, file_path, converted if converted is not None else original_content
        )
        text = await _pdf_to_text(client, ocr_pdf)
    await service.save_extracted_text(db, doc.id, text, ocr_engine="stirling")
    if text.strip():
        from app.documents.review_service import prepare_review
        from app.finance.bills_schemas import MutationContext

        revision = await prepare_review(
            db,
            doc.user_id,
            doc.id,
            refresh=True,
            context=MutationContext(
                idempotency_key=f"ocr-review:{doc.id}:{doc.attempt_count}", performed_by="system"
            ),
        )
        await process_review_revision(db, revision.id)


async def process_document(ctx, document_id: str) -> None:
    doc_id = uuid.UUID(document_id)
    async with async_session_factory() as db:
        # Keep the claim and results in one transaction. A crash rolls back to
        # pending and the dispatcher redelivers; concurrent deliveries skip it.
        doc = (
            await db.execute(
                select(Document).where(Document.id == doc_id).with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if doc is None or doc.status not in {DocumentStatus.PENDING, DocumentStatus.PROCESSING}:
            return
        if doc.next_attempt_at is not None and doc.next_attempt_at > datetime.now(UTC):
            return
        if doc.attempt_count >= settings.DOCUMENT_MAX_ATTEMPTS:
            doc.status = DocumentStatus.ERROR
            doc.next_attempt_at = None
            await db.commit()
            return
        doc.attempt_count += 1
        doc.status = DocumentStatus.PROCESSING
        doc.next_attempt_at = None
        await db.flush()
        try:
            # A savepoint rolls back failed writes without releasing the claim.
            async with db.begin_nested():
                await _process_content(db, doc)
            doc.status = DocumentStatus.DONE
            doc.last_error_code = None
        except (
            OSError,
            httpx.HTTPError,
            SQLAlchemyError,
            ValueError,
            KeyError,
            TypeError,
            RuntimeError,
        ) as error:
            await db.refresh(doc)
            logger.warning("OCR processing failed for document %s", doc_id)
            retryable = is_retryable_ocr_error(error)
            if isinstance(error, service.DocumentIntegrityError):
                doc.last_error_code = "integrity_mismatch"
            elif isinstance(error, OCRResponseTooLargeError):
                doc.last_error_code = "output_limit"
            else:
                doc.last_error_code = "upstream_unavailable" if retryable else "processing_failed"
            if retryable and doc.attempt_count < settings.DOCUMENT_MAX_ATTEMPTS:
                doc.status = DocumentStatus.PENDING
                doc.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=retry_delay_seconds(doc.attempt_count)
                )
            else:
                doc.status = DocumentStatus.ERROR
                doc.next_attempt_at = None
        await db.commit()


async def prepare_document_review(ctx, revision_id: str) -> None:
    async with async_session_factory() as db:
        revision = await process_review_revision(db, uuid.UUID(revision_id))
        if revision is not None:
            await db.commit()


class WorkerSettings:
    functions: ClassVar = [process_document, prepare_document_review]
    redis_settings: ClassVar = REDIS_SETTINGS
    cron_jobs: ClassVar = [
        cron(dispatch_pending_documents, second={0, 30}, run_at_startup=True),
        cron(dispatch_pending_document_reviews, second={15, 45}, run_at_startup=True),
    ]
    keep_result = 0
    job_timeout = settings.DOCUMENT_JOB_TIMEOUT_SECONDS
