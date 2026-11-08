"""Private PDF/CSV admission without creating OCR, review or AI jobs."""

import asyncio
import csv
import io
import re
import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.documents import service
from app.documents.models import Document
from app.documents.upload_limits import enforce_storage_admission
from app.documents.validation import UnsupportedDocumentFormatError, validate_document_content

REVOLUT_COLUMNS = frozenset(
    {
        "Rodzaj",
        "Produkt",
        "Data rozpoczęcia",
        "Data zrealizowania",
        "Opis",
        "Kwota",
        "Opłata",
        "Waluta",
        "State",
        "Saldo",
    }
)


class ImportStorageError(ValueError):
    def __init__(self, code: str, http_status: int = 422) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(code)


def validate_import_csv(content: bytes) -> None:
    if b"\x00" in content:
        raise ImportStorageError("csv_invalid")
    try:
        rows = csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
        headers = next(rows)
        if len(headers) != len(REVOLUT_COLUMNS) or set(headers) != REVOLUT_COLUMNS:
            raise ImportStorageError("csv_layout_unsupported")
        count = 0
        for row in rows:
            if not row:
                continue
            count += 1
            if count > settings.FINANCE_IMPORT_MAX_CSV_ROWS:
                raise ImportStorageError("csv_row_limit", 413)
            if len(row) != len(headers):
                raise ImportStorageError("csv_incomplete_record")
        if count == 0:
            raise ImportStorageError("csv_empty")
    except (UnicodeDecodeError, csv.Error, StopIteration) as error:
        raise ImportStorageError("csv_invalid") from error


def read_import_original(document: Document) -> bytes:
    """Use canonical content-addressed paths, not user-supplied paths or symlinks."""
    if not re.fullmatch(r"[0-9a-f]{64}", document.sha256_hash):
        raise ImportStorageError("source_integrity_failed")
    relative = Path(service._storage_path(document.sha256_hash))
    if Path(document.storage_path) != relative:
        raise ImportStorageError("source_integrity_failed")
    root = service.UPLOAD_DIR.resolve()
    path = service.UPLOAD_DIR / relative
    try:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ImportStorageError("source_integrity_failed")
        with path.open("rb") as stream:
            content = stream.read(settings.DOCUMENT_MAX_FILE_BYTES + 1)
        if (
            len(content) != document.size_bytes
            or service.compute_sha256(content) != document.sha256_hash
        ):
            raise ImportStorageError("source_integrity_failed")
        if len(content) > settings.DOCUMENT_MAX_FILE_BYTES:
            raise ImportStorageError("source_size_limit", 413)
        return content
    except OSError as error:
        raise ImportStorageError("source_integrity_failed") from error


async def store_import_document(
    db: AsyncSession,
    owner: uuid.UUID,
    *,
    filename: str,
    content: bytes,
) -> tuple[Document, bool]:
    if not content:
        raise ImportStorageError("source_empty")
    if len(content) > settings.DOCUMENT_MAX_FILE_BYTES:
        raise ImportStorageError("source_size_limit", 413)
    safe_name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not safe_name or len(safe_name) > 500 or any(ord(char) < 32 for char in safe_name):
        raise ImportStorageError("source_filename_invalid")
    suffix = Path(safe_name).suffix.lower()
    if suffix == ".pdf" and content.startswith(b"%PDF-"):
        try:
            await validate_document_content(content, "application/pdf")
        except UnsupportedDocumentFormatError as error:
            raise ImportStorageError("pdf_invalid") from error
        mime_type = "application/pdf"
    elif suffix == ".csv" and not content.startswith(b"%PDF-"):
        await asyncio.to_thread(validate_import_csv, content)
        mime_type = "text/csv"
    else:
        raise ImportStorageError("source_format_unsupported")
    sha256 = service.compute_sha256(content)
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("document-storage-admission")))
    )
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"document-upload:{owner}:{sha256}")))
    )
    existing = await db.scalar(
        select(Document).where(Document.user_id == owner, Document.sha256_hash == sha256)
    )
    if existing is not None:
        if existing.archived_at is not None:
            raise ImportStorageError("document_archived", 409)
        await asyncio.to_thread(read_import_original, existing)
        return existing, True
    await enforce_storage_admission(db, owner, len(content), service.UPLOAD_DIR)
    await asyncio.to_thread(service._write_document_content, sha256, content)
    document = Document(
        user_id=owner,
        filename=safe_name,
        original_name=safe_name,
        mime_type=mime_type,
        sha256_hash=sha256,
        size_bytes=len(content),
        storage_path=service._storage_path(sha256),
        processing_method="bank_import",
        status="done",
    )
    db.add(document)
    await db.flush([document])
    return document, False
