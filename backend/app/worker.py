import uuid

import httpx
from arq import create_pool
from arq.connections import RedisSettings, ArqRedis
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.documents import service
from app.documents.models import Document
from app.documents.schemas import DocumentStatus

REDIS_SETTINGS = RedisSettings(host="redis", port=6379, database=1)
STIRLING_OCR_URL = f"{settings.STIRLING_PDF_URL}/api/v1/misc/ocr-pdf"
STIRLING_IMG_TO_PDF_URL = f"{settings.STIRLING_PDF_URL}/api/v1/convert/img/pdf"


async def enqueue_process_document(document_id: str):
    redis: ArqRedis = await create_pool(REDIS_SETTINGS)
    await redis.enqueue_job("process_document", document_id)
    await redis.close()


async def _convert_image_to_pdf(client: httpx.AsyncClient, file_path: str) -> bytes:
    with open(file_path, "rb") as f:
        files = {"fileInput": f}
        response = await client.post(STIRLING_IMG_TO_PDF_URL, files=files)
        response.raise_for_status()
        return response.content


async def _ocr_pdf(client: httpx.AsyncClient, file_path: str) -> str:
    with open(file_path, "rb") as f:
        files = {"fileInput": f}
        data = {"languages": "pol,eng", "ocrType": "skip-text", "sidecar": "true"}
        response = await client.post(STIRLING_OCR_URL, files=files, data=data)
        response.raise_for_status()
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
                    pdf_content = await _convert_image_to_pdf(client, ocr_file)
                    pdf_path = file_path.parent / f"{doc.sha256_hash}.pdf"
                    pdf_path.write_bytes(pdf_content)
                    ocr_file = str(pdf_path)

                text = await _ocr_pdf(client, ocr_file)

            await service.save_extracted_text(db, doc_id, text, ocr_engine="stirling")
            await service.update_document_status(db, doc_id, DocumentStatus.DONE)
            await db.commit()

        except Exception as e:
            await service.save_extracted_text(db, doc_id, f'{{"error": "{str(e)}"}}', ocr_engine="stirling")
            await service.update_document_status(db, doc_id, DocumentStatus.ERROR)
            await db.commit()


class WorkerSettings:
    functions = [process_document]
    redis_settings = REDIS_SETTINGS
