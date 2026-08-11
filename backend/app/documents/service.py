import hashlib
import uuid
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document, DocumentText
from app.documents.schemas import DocumentStatus


UPLOAD_DIR = Path("/app/uploads")


def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _storage_path(sha256_hash: str) -> str:
    return f"{sha256_hash[:2]}/{sha256_hash}"


def _ensure_storage_dir(sha256_hash: str):
    dir_path = UPLOAD_DIR / sha256_hash[:2]
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


async def upload_document(
    db: AsyncSession,
    user_id: uuid.UUID,
    content: bytes,
    original_name: str,
    mime_type: str,
) -> Document:
    sha256_hash = compute_sha256(content)
    existing = await db.execute(
        select(Document).where(Document.user_id == user_id, Document.sha256_hash == sha256_hash)
    )
    existing_doc = existing.scalar_one_or_none()
    if existing_doc is not None:
        return existing_doc

    storage_dir = _ensure_storage_dir(sha256_hash)
    file_path = storage_dir / sha256_hash
    if not file_path.exists():
        file_path.write_bytes(content)

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
    return doc


async def update_document_status(db: AsyncSession, document_id: uuid.UUID, status: str) -> Document | None:
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
    doc_text = DocumentText(
        document_id=document_id,
        extracted_text=text,
        ocr_engine=ocr_engine,
        extracted_at=datetime.now(timezone.utc),
    )
    db.add(doc_text)
    await db.flush()
    return doc_text


async def get_documents(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 50, offset: int = 0, status: str | None = None
) -> list[Document]:
    stmt = select(Document).where(Document.user_id == user_id).order_by(Document.created_at.desc())
    if status:
        stmt = stmt.where(Document.status == status)
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_document(db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
    result = await db.execute(select(Document).where(Document.id == document_id, Document.user_id == user_id))
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
