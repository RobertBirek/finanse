"""Bounded HTTP helpers shared by legacy and vision OCR pipelines."""

import asyncio
from pathlib import Path

import httpx

from app.config import settings
from app.documents.ocr_client import OCRResponseTooLargeError, post_bounded

STIRLING_OCR_URL = f"{settings.STIRLING_PDF_URL}/api/v1/misc/ocr-pdf"
STIRLING_IMG_TO_PDF_URL = f"{settings.STIRLING_PDF_URL}/api/v1/convert/img/pdf"
STIRLING_PDF_TO_TEXT_URL = f"{settings.STIRLING_PDF_URL}/api/v1/convert/pdf/text"


async def _convert_image_to_pdf(
    client: httpx.AsyncClient, file_path: str, image_content: bytes | None = None
) -> bytes:
    path = Path(file_path)
    content = image_content if image_content is not None else await asyncio.to_thread(path.read_bytes)
    files = {"fileInput": (path.name, content)}
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
    return await post_bounded(client, STIRLING_OCR_URL, files, settings.DOCUMENT_OCR_MAX_BYTES, data)


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
