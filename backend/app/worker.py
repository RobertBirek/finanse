import asyncio
import logging
import uuid
from pathlib import Path
from typing import ClassVar

import httpx
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from openai import OpenAIError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import async_session_factory
from app.documents import service
from app.documents.models import Document
from app.documents.schemas import DocumentStatus

logger = logging.getLogger(__name__)

REDIS_SETTINGS = RedisSettings(host="redis", port=6379, database=1)
STIRLING_OCR_URL = f"{settings.STIRLING_PDF_URL}/api/v1/misc/ocr-pdf"
STIRLING_IMG_TO_PDF_URL = f"{settings.STIRLING_PDF_URL}/api/v1/convert/img/pdf"
STIRLING_PDF_TO_TEXT_URL = f"{settings.STIRLING_PDF_URL}/api/v1/convert/pdf/txt"


async def enqueue_process_document(document_id: str):
    redis: ArqRedis = await create_pool(REDIS_SETTINGS)
    await redis.enqueue_job("process_document", document_id)
    await redis.close()


async def _convert_image_to_pdf(client: httpx.AsyncClient, file_path: str) -> bytes:
    content = await asyncio.to_thread(Path(file_path).read_bytes)
    files = {"fileInput": (Path(file_path).name, content)}
    response = await client.post(STIRLING_IMG_TO_PDF_URL, files=files)
    response.raise_for_status()
    return response.content


async def _ocr_pdf(client: httpx.AsyncClient, file_path: str) -> bytes:
    """Run OCR on PDF, return searchable PDF bytes."""
    content = await asyncio.to_thread(Path(file_path).read_bytes)
    files = {"fileInput": (Path(file_path).name, content)}
    data = {"languages": "pol,eng", "ocrType": "skip-text"}
    response = await client.post(STIRLING_OCR_URL, files=files, data=data)
    response.raise_for_status()
    return response.content


async def _pdf_to_text(client: httpx.AsyncClient, pdf_content: bytes) -> str:
    """Extract text from PDF content."""
    files = {"fileInput": ("output.pdf", pdf_content, "application/pdf")}
    response = await client.post(STIRLING_PDF_TO_TEXT_URL, files=files)
    if response.status_code != 200:
        return f"[Text extraction failed: HTTP {response.status_code}]"
    return response.text


async def process_document(ctx, document_id: str) -> None:
    doc_id = uuid.UUID(document_id)
    upload_dir = service.UPLOAD_DIR

    async with async_session_factory() as db:
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if doc is None:
            return

        await service.update_document_status(db, doc_id, DocumentStatus.PROCESSING)
        await db.commit()

        try:
            file_path = upload_dir / doc.storage_path

            async with httpx.AsyncClient(timeout=120.0) as client:
                ocr_file = str(file_path)
                if doc.mime_type and doc.mime_type.startswith("image/"):
                    await _convert_image_to_pdf(client, ocr_file)

                # Step 1: OCR → searchable PDF
                ocr_pdf = await _ocr_pdf(client, ocr_file)

                # Step 2: PDF → text
                text = await _pdf_to_text(client, ocr_pdf)

            await service.save_extracted_text(db, doc_id, text, ocr_engine="stirling")
            await service.update_document_status(db, doc_id, DocumentStatus.DONE)
            await db.commit()

            # Step 3: Extract financial data via OpenAI
            try:
                from app.documents.extractor import (
                    create_inbox_from_document,
                    extract_financial_data,
                )

                data = await extract_financial_data(text)
                if data.get("detected"):
                    await create_inbox_from_document(
                        db, doc.user_id, doc.id, doc.original_name, data
                    )
                    # Reload doc after potential state change
                    result = await db.execute(select(Document).where(Document.id == doc_id))
                    doc = result.scalar_one_or_none()
                    if doc and doc.status == DocumentStatus.DONE:
                        doc.status = DocumentStatus.DONE  # keep done
                    await db.commit()
            except (OpenAIError, SQLAlchemyError, ValueError, KeyError, TypeError) as exc:
                logger.warning("Financial extraction failed for document %s: %s", doc_id, exc)

        except (OSError, httpx.HTTPError, SQLAlchemyError, ValueError, KeyError, TypeError) as e:
            await service.save_extracted_text(
                db, doc_id, f'{{"error": "{e!s}"}}', ocr_engine="stirling"
            )
            await service.update_document_status(db, doc_id, DocumentStatus.ERROR)
            await db.commit()


class WorkerSettings:
    functions: ClassVar = [process_document]
    redis_settings: ClassVar = REDIS_SETTINGS
