import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import httpx
from arq import create_pool, cron
from arq.connections import ArqRedis, RedisSettings
from openai import OpenAIError
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import async_session_factory
from app.documents import service
from app.documents.models import Document
from app.documents.schemas import DocumentStatus

logger = logging.getLogger(__name__)

REDIS_SETTINGS = RedisSettings.from_dsn(settings.REDIS_URL)
STIRLING_OCR_URL = f"{settings.STIRLING_PDF_URL}/api/v1/misc/ocr-pdf"
STIRLING_IMG_TO_PDF_URL = f"{settings.STIRLING_PDF_URL}/api/v1/convert/img/pdf"
STIRLING_PDF_TO_TEXT_URL = f"{settings.STIRLING_PDF_URL}/api/v1/convert/pdf/txt"


async def enqueue_process_document(document_id: str) -> None:
    redis: ArqRedis = await create_pool(REDIS_SETTINGS)
    try:
        await redis.enqueue_job("process_document", document_id, _job_id=f"document:{document_id}")
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
                            Document.status == DocumentStatus.PENDING,
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


async def _convert_image_to_pdf(client: httpx.AsyncClient, file_path: str) -> bytes:
    path = Path(file_path)
    content = await asyncio.to_thread(path.read_bytes)
    files = {"fileInput": (path.name, content)}
    response = await client.post(STIRLING_IMG_TO_PDF_URL, files=files)
    response.raise_for_status()
    return response.content


async def _ocr_pdf(
    client: httpx.AsyncClient, file_path: str, pdf_content: bytes | None = None
) -> bytes:
    """Use converted PDF bytes for images without changing their original files."""
    path = Path(file_path)
    content = pdf_content if pdf_content is not None else await asyncio.to_thread(path.read_bytes)
    files = {"fileInput": (path.name, content)}
    data = {"languages": "pol,eng", "ocrType": "skip-text"}
    response = await client.post(STIRLING_OCR_URL, files=files, data=data)
    response.raise_for_status()
    return response.content


async def _pdf_to_text(client: httpx.AsyncClient, pdf_content: bytes) -> str:
    files = {"fileInput": ("output.pdf", pdf_content, "application/pdf")}
    response = await client.post(STIRLING_PDF_TO_TEXT_URL, files=files)
    response.raise_for_status()
    return response.text


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
        doc.status = DocumentStatus.PROCESSING
        await db.flush()
        try:
            file_path = str(service.UPLOAD_DIR / doc.storage_path)
            async with httpx.AsyncClient(timeout=120.0) as client:
                converted = None
                if doc.mime_type.startswith("image/"):
                    converted = await _convert_image_to_pdf(client, file_path)
                ocr_pdf = await _ocr_pdf(client, file_path, converted)
                text = await _pdf_to_text(client, ocr_pdf)
            await service.save_extracted_text(db, doc_id, text, ocr_engine="stirling")

            # Optional extraction cannot roll back a successful OCR result.
            try:
                from app.documents.extractor import (
                    create_inbox_from_document,
                    extract_financial_data,
                )

                async with db.begin_nested():
                    data = await extract_financial_data(text)
                    if data.get("detected"):
                        await create_inbox_from_document(
                            db, doc.user_id, doc.id, doc.original_name, data
                        )
            except (
                OpenAIError,
                SQLAlchemyError,
                ValueError,
                KeyError,
                TypeError,
                RuntimeError,
                AttributeError,
            ):
                logger.warning("Financial extraction failed for document %s", doc_id)

            doc.status = DocumentStatus.DONE
            await db.commit()
        except (
            OSError,
            httpx.HTTPError,
            SQLAlchemyError,
            ValueError,
            KeyError,
            TypeError,
            RuntimeError,
        ):
            await db.rollback()
            logger.warning("OCR processing failed for document %s", doc_id)
            await service.update_document_status(db, doc_id, DocumentStatus.ERROR)
            await db.commit()


class WorkerSettings:
    functions: ClassVar = [process_document]
    redis_settings: ClassVar = REDIS_SETTINGS
    cron_jobs: ClassVar = [cron(dispatch_pending_documents, second={0, 30}, run_at_startup=True)]
    keep_result = 0
    job_timeout = settings.DOCUMENT_JOB_TIMEOUT_SECONDS
