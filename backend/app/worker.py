import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import httpx
from arq import create_pool, cron
from arq.connections import ArqRedis, RedisSettings
from arq.worker import func
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.documents import service
from app.documents.images import normalize_image
from app.documents.job_models import DocumentProcessingJob
from app.documents.models import Document
from app.documents.ocr_client import OCRResponseTooLargeError
from app.documents.ocr_pipeline import (
    STIRLING_IMG_TO_PDF_URL,  # noqa: F401
    STIRLING_OCR_URL,  # noqa: F401
    STIRLING_PDF_TO_TEXT_URL,  # noqa: F401
    _convert_image_to_pdf,
    _ocr_pdf,
    _pdf_to_text,
)
from app.documents.receipt_read_worker import dispatch_receipt_reads, process_receipt_read
from app.documents.retry import is_retryable_ocr_error, retry_delay_seconds
from app.documents.review_service import pending_review_ids, process_review_revision
from app.documents.schemas import DocumentStatus
from app.finance.proposal_state import expire_proposal_items
from app.finance.rule_worker import dispatch_rule_events, process_rule_event
from app.finance.suggestion_worker import dispatch_suggestion_jobs, process_suggestion_job

logger = logging.getLogger(__name__)

REDIS_SETTINGS = RedisSettings.from_dsn(settings.REDIS_URL)


async def expire_category_proposals(ctx) -> None:
    async with async_session_factory() as db:
        await expire_proposal_items(
            db, datetime.now(UTC), limit=settings.FINANCE_SUGGESTIONS_DISPATCH_BATCH
        )
        await db.commit()


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


async def enqueue_process_document_job(job_id: str) -> None:
    redis: ArqRedis = await create_pool(REDIS_SETTINGS)
    try:
        await redis.enqueue_job("process_document_job", job_id, _job_id=f"document-job:{job_id}")
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
                        Document.processing_method == "legacy_ocr",
                        Document.archived_at.is_(None),
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
                        ),
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


async def dispatch_document_jobs(ctx) -> None:
    """Deliver durable vision/local-OCR intents; legacy rows never enter this queue."""
    from app.documents.job_service import recover_processing_jobs

    now = datetime.now(UTC)
    async with async_session_factory() as db:
        recovered = await recover_processing_jobs(
            db, now=now, limit=settings.DOCUMENT_DISPATCH_BATCH_SIZE
        )
        pending = list(
            (
                await db.execute(
                    select(DocumentProcessingJob.id)
                    .join(Document, Document.id == DocumentProcessingJob.document_id)
                    .where(
                        Document.archived_at.is_(None),
                        DocumentProcessingJob.state == "pending",
                        (DocumentProcessingJob.next_attempt_at.is_(None))
                        | (DocumentProcessingJob.next_attempt_at <= now),
                    )
                    .order_by(DocumentProcessingJob.created_at)
                    .limit(settings.DOCUMENT_DISPATCH_BATCH_SIZE)
                )
            ).scalars()
        )
        await db.commit()
    for job_id in dict.fromkeys([*recovered, *pending]):
        await ctx["redis"].enqueue_job(
            "process_document_job", str(job_id), _job_id=f"document-job:{job_id}"
        )


async def _process_content(db: AsyncSession, doc: Document) -> None:
    document_path = service.UPLOAD_DIR / doc.storage_path
    file_path = str(document_path)
    original_content = await asyncio.to_thread(
        service.read_verified_document_content, document_path, doc.sha256_hash
    )
    async with httpx.AsyncClient(timeout=120.0) as client:
        converted = None
        if doc.mime_type.startswith("image/"):
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
        if getattr(doc, "archived_at", None) is not None:
            return
        if getattr(doc, "processing_method", "legacy_ocr") != "legacy_ocr":
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


async def process_document_job(ctx, job_id: str) -> None:
    """Route durable jobs without letting image revisions use the legacy text worker."""
    from app.documents.vision_worker import process_document_job as process_vision_job

    async with async_session_factory() as db:
        job = await db.get(DocumentProcessingJob, uuid.UUID(job_id))
        kind = job.kind if job is not None else None
    if kind == "vision":
        await process_vision_job(ctx, job_id)
    elif kind == "local_ocr":
        await process_local_ocr_job(ctx, job_id)


async def process_local_ocr_job(ctx, job_id: str) -> None:
    """Explicit local OCR stores text only; it never prepares an LLM review."""
    del ctx
    from app.documents.job_service import JobOutcome, claim_processing_job, finish_processing_job

    now = datetime.now(UTC)
    async with async_session_factory() as db:
        claim = await claim_processing_job(db, uuid.UUID(job_id), now=now)
        await db.commit()
    if claim is None or claim.kind != "local_ocr":
        return
    async with async_session_factory() as db:
        document = await db.get(Document, claim.document_id)
    if document is None:
        return
    try:
        source = await asyncio.to_thread(
            service.read_verified_document_content,
            service.UPLOAD_DIR / document.storage_path,
            document.sha256_hash,
        )
        image = await normalize_image(source, document.mime_type)
        async with httpx.AsyncClient(timeout=120.0) as client:
            converted = await _convert_image_to_pdf(client, "document.jpg", image)
            ocr_pdf = await _ocr_pdf(client, "document.pdf", converted)
            text = await _pdf_to_text(client, ocr_pdf)
        async with async_session_factory() as db:
            # Recheck the local lease through the same CAS path before publishing text.
            if await finish_processing_job(
                db, claim, JobOutcome(completed=True), now=datetime.now(UTC)
            ):
                await service.save_extracted_text(
                    db, claim.document_id, text, ocr_engine="stirling"
                )
            await db.commit()
    except (OSError, httpx.HTTPError, ValueError, RuntimeError):
        async with async_session_factory() as db:
            await finish_processing_job(
                db,
                claim,
                JobOutcome(error_code="local_ocr_failed", retryable=True),
                now=datetime.now(UTC),
            )
            await db.commit()


class WorkerSettings:
    functions: ClassVar = [
        process_document,
        prepare_document_review,
        process_document_job,
        func(
            process_receipt_read,
            name="process_receipt_read",
            timeout=settings.DOCUMENT_JOB_TIMEOUT_SECONDS,
            max_tries=1,
        ),
        process_rule_event,
        func(
            process_suggestion_job,
            name="process_suggestion_job",
            timeout=settings.FINANCE_SUGGESTIONS_JOB_TIMEOUT_SECONDS,
            max_tries=1,
        ),
    ]
    redis_settings: ClassVar = REDIS_SETTINGS
    cron_jobs: ClassVar = [
        cron(dispatch_pending_documents, second={0, 30}, run_at_startup=True),
        cron(dispatch_pending_document_reviews, second={15, 45}, run_at_startup=True),
        cron(dispatch_document_jobs, second={5, 35}, run_at_startup=True),
        cron(dispatch_receipt_reads, second={7, 37}, run_at_startup=True),
        cron(dispatch_rule_events, second={10, 40}, run_at_startup=True),
        cron(dispatch_suggestion_jobs, second={20, 50}, run_at_startup=True),
        cron(expire_category_proposals, second={25, 55}, run_at_startup=True),
    ]
    keep_result = 0
    job_timeout = settings.DOCUMENT_JOB_TIMEOUT_SECONDS
