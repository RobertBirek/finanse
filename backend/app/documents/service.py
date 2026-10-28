import asyncio
import fcntl
import hashlib
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document, DocumentText
from app.documents.schemas import DocumentStatus
from app.documents.upload_limits import enforce_storage_admission
from app.documents.validation import (
    UnsupportedDocumentFormatError,
    validate_document_content,
)
from app.documents.validation_process import detect_document_mime_type

__all__ = ["UnsupportedDocumentFormatError", "detect_document_mime_type"]

UPLOAD_DIR = Path("/app/uploads")


class DocumentIntegrityError(OSError):
    pass


def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_verified_document_content(file_path: Path, expected_sha256: str) -> bytes:
    """Read a stored document and fail if its contents differ from its recorded hash."""
    content = file_path.read_bytes()
    if compute_sha256(content) != expected_sha256:
        raise DocumentIntegrityError("Stored document failed integrity verification")
    return content


def _storage_path(sha256_hash: str) -> str:
    return f"{sha256_hash[:2]}/{sha256_hash}"


def _ensure_storage_dir(sha256_hash: str) -> Path:
    dir_path = UPLOAD_DIR / sha256_hash[:2]
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def _write_document_content(sha256_hash: str, content: bytes) -> None:
    lock_path = UPLOAD_DIR / ".backup.lock"
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            storage_dir = _ensure_storage_dir(sha256_hash)
            file_path = storage_dir / sha256_hash
            if file_path.exists():
                if compute_sha256(file_path.read_bytes()) != sha256_hash:
                    raise OSError("Stored document failed integrity verification")
                return
            # Never publish a partial original, even if writing/fsync is interrupted.
            # link() creates the final name atomically without overwriting originals.
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=storage_dir, prefix=".upload-", delete=False
                ) as temporary:
                    temporary_path = Path(temporary.name)
                    temporary.write(content)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.link(temporary_path, file_path)
                for directory in (storage_dir, UPLOAD_DIR):
                    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


async def store_document(
    db: AsyncSession,
    user_id: uuid.UUID,
    content: bytes,
    original_name: str,
    mime_type: str,
) -> tuple[Document, bool]:
    """Store content and return an explicit duplicate flag under a per-content lock."""
    mime_type = await validate_document_content(content, mime_type)

    sha256_hash = compute_sha256(content)
    # Global lock serializes quota admission across users until the DB commit.
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("document-storage-admission")))
    )
    await db.execute(
        select(
            func.pg_advisory_xact_lock(func.hashtext(f"document-upload:{user_id}:{sha256_hash}"))
        )
    )
    existing = await db.execute(
        select(Document).where(Document.user_id == user_id, Document.sha256_hash == sha256_hash)
    )
    existing_doc = existing.scalar_one_or_none()
    if existing_doc is not None:
        await asyncio.to_thread(_write_document_content, sha256_hash, content)
        return existing_doc, True

    await enforce_storage_admission(db, user_id, len(content), UPLOAD_DIR)
    await asyncio.to_thread(_write_document_content, sha256_hash, content)
    doc = Document(
        user_id=user_id,
        filename=original_name,
        original_name=original_name,
        mime_type=mime_type,
        sha256_hash=sha256_hash,
        size_bytes=len(content),
        storage_path=_storage_path(sha256_hash),
        status=DocumentStatus.PENDING,
    )
    db.add(doc)
    await db.flush()
    return doc, False


async def upload_document(
    db: AsyncSession, user_id: uuid.UUID, content: bytes, original_name: str, mime_type: str
) -> Document:
    document, _duplicate = await store_document(db, user_id, content, original_name, mime_type)
    return document


async def update_document_status(
    db: AsyncSession, document_id: uuid.UUID, status: str
) -> Document | None:
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        return None
    doc.status = status
    await db.flush()
    return doc


async def save_extracted_text(
    db: AsyncSession, document_id: uuid.UUID, text: str, ocr_engine: str = "stirling"
) -> DocumentText:
    values = {
        "document_id": document_id,
        "extracted_text": text,
        "ocr_engine": ocr_engine,
        "extracted_at": datetime.now(UTC),
    }
    statement = (
        insert(DocumentText)
        .values(**values)
        .on_conflict_do_update(index_elements=[DocumentText.document_id], set_=values)
        .returning(DocumentText)
    )
    return (await db.execute(statement, execution_options={"populate_existing": True})).scalar_one()


async def get_documents(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> list[Document]:
    stmt = select(Document).where(Document.user_id == user_id).order_by(Document.created_at.desc())
    if status:
        stmt = stmt.where(Document.status == status)
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_document(
    db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID
) -> Document | None:
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_document_text(db: AsyncSession, document_id: uuid.UUID) -> DocumentText | None:
    result = await db.execute(select(DocumentText).where(DocumentText.document_id == document_id))
    return result.scalar_one_or_none()


async def delete_document(db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID) -> bool:
    doc = await get_document(db, user_id, document_id)
    if doc is None:
        return False
    await db.delete(doc)
    await db.flush()
    return True
