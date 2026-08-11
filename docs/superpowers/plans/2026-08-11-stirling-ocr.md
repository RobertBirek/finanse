# Stirling PDF + OCR Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Document upload and OCR pipeline: drag & drop + camera capture → Stirling PDF OCR → extracted text → document list with status tracking.

**Architecture:** FastAPI documents service (upload, list, get text) → ARQ worker (async OCR via Stirling PDF) → React frontend (upload with drag & drop + camera, document list with status badges, text viewer).

**Tech Stack:** FastAPI, SQLAlchemy, ARQ (Redis), Stirling PDF, httpx, React, TanStack Query, Tailwind CSS

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/documents/service.py` | Create | Upload, hash, store, list, get, delete |
| `backend/app/documents/schemas.py` | Create | Pydantic request/response schemas |
| `backend/app/documents/router.py` | Modify | Full REST endpoints |
| `backend/app/worker.py` | Create | ARQ worker + process_document task |
| `backend/requirements.txt` | Modify | Add arq dependency |
| `docker/finanse/compose.yaml` | Modify | Start stirling, add worker service |
| `frontend/src/api/documents.ts` | Create | TanStack Query hooks |
| `frontend/src/pages/Documents.tsx` | Create | Main page |
| `frontend/src/components/DocumentUpload.tsx` | Create | Upload zone + camera button |
| `frontend/src/components/DocumentList.tsx` | Create | Document list with status badges |
| `frontend/src/components/DocumentViewer.tsx` | Create | Text preview modal |
| `frontend/src/App.tsx` | Modify | Add /documents route |
| `frontend/src/components/Layout.tsx` | Modify | Add navigation link |

---

### Task 1: Infrastructure — Stirling PDF + ARQ + compose

**Files:**
- Modify: `docker/finanse/compose.yaml`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Start Stirling PDF and add Polish OCR**

Pull image and download Polish tessdata:

```bash
# Pull Stirling PDF
cd /docker/finanse && docker compose pull stirling-pdf

# Download Polish Tesseract language pack
wget -O /docker/finanse/data/stirling/trainingData/pol.traineddata \
  https://github.com/tesseract-ocr/tessdata/raw/main/pol.traineddata

# Start Stirling
cd /docker/finanse && docker compose up -d stirling-pdf
```

Verify Stirling is running:

```bash
docker exec finanse-stirling curl -s http://localhost:8080/api/v1/info/status
# Expected: {"version": "..."}
```

- [ ] **Step 2: Add ARQ to requirements**

Add to `backend/requirements.txt`:

```
arq>=0.26.0
```

Also add to `backend/pyproject.toml` dependencies:

```toml
"arq>=0.26.0",
```

- [ ] **Step 3: Build and install updated dependencies**

```bash
cd /opt/finanse/backend && docker compose -f /docker/finanse/compose.yaml build backend
cd /docker/finanse && docker compose up -d backend
```

- [ ] **Step 4: Add worker service to compose**

Add to `/docker/finanse/compose.yaml` after the backend service:

```yaml
  worker:
    build:
      context: /opt/finanse/backend
      dockerfile: Dockerfile
    container_name: finanse-worker
    restart: unless-stopped
    environment:
      DATABASE_URL: ${DATABASE_URL}
      REDIS_URL: ${REDIS_URL}
      STIRLING_PDF_URL: ${STIRLING_PDF_URL}
      ENVIRONMENT: ${ENVIRONMENT}
    volumes:
      - /opt/finanse/backend:/app
      - ./data/uploads:/app/uploads
    networks:
      - internal
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      stirling-pdf:
        condition: service_started
    command: arq app.worker.WorkerSettings --burst
```

The `--burst` flag means: process all queued jobs, then exit. For now we use burst mode (simple). Later we can switch to continuous mode with `--watch`.

Start the worker:

```bash
cd /docker/finanse && docker compose up -d worker
```

- [ ] **Step 5: Commit infrastructure changes**

```bash
git add docker/finanse/compose.yaml backend/requirements.txt backend/pyproject.toml
git commit -m "feat: add Stirling PDF, ARQ worker, Polish OCR to infrastructure"
```

---

### Task 2: Documents service + schemas

**Files:**
- Create: `backend/app/documents/service.py`
- Create: `backend/app/documents/schemas.py`
- Create: `backend/tests/test_documents/test_service.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_documents/__init__.py` (empty) and `backend/tests/test_documents/test_service.py`:

```python
import hashlib
import io
import uuid

import pytest
from app.documents.schemas import DocumentCreate, DocumentResponse, DocumentStatus
from app.documents.service import (
    compute_sha256,
    upload_document,
    get_documents,
    get_document,
    get_document_text,
)
from app.documents.models import Document


class TestComputeSha256:
    def test_computes_hash(self):
        content = b"hello world"
        expected = hashlib.sha256(content).hexdigest()
        result = compute_sha256(content)
        assert result == expected
        assert len(result) == 64

    def test_different_content_different_hash(self):
        h1 = compute_sha256(b"a")
        h2 = compute_sha256(b"b")
        assert h1 != h2


class TestDocumentService:
    @pytest.mark.asyncio
    async def test_upload_creates_document(self, db_session):
        user_id = uuid.uuid4()
        content = b"%PDF-1.4 test pdf content"
        filename = "test.pdf"

        doc = await upload_document(
            db_session, user_id, content, filename, "application/pdf"
        )

        assert doc.id is not None
        assert doc.original_name == "test.pdf"
        assert doc.filename == doc.original_name
        assert doc.mime_type == "application/pdf"
        assert doc.size_bytes == len(content)
        assert doc.sha256_hash == compute_sha256(content)
        assert doc.status == "pending"
        assert doc.storage_path.startswith(doc.sha256_hash[:2])

    @pytest.mark.asyncio
    async def test_upload_deduplicates_same_hash(self, db_session):
        user_id = uuid.uuid4()
        content = b"same content"

        doc1 = await upload_document(
            db_session, user_id, content, "a.pdf", "application/pdf"
        )
        doc2 = await upload_document(
            db_session, user_id, content, "b.pdf", "application/pdf"
        )

        assert doc1.id == doc2.id  # same document returned
        assert doc1.original_name == "a.pdf"  # first name preserved

    @pytest.mark.asyncio
    async def test_list_returns_by_user(self, db_session):
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()

        await upload_document(db_session, user_a, b"aaa", "a.pdf", "application/pdf")
        await upload_document(db_session, user_b, b"bbb", "b.pdf", "application/pdf")

        docs_a = await get_documents(db_session, user_a)
        docs_b = await get_documents(db_session, user_b)

        assert len(docs_a) == 1
        assert len(docs_b) == 1
        assert docs_a[0].original_name == "a.pdf"

    @pytest.mark.asyncio
    async def test_get_document_by_id(self, db_session):
        user_id = uuid.uuid4()
        doc = await upload_document(
            db_session, user_id, b"test", "doc.pdf", "application/pdf"
        )

        found = await get_document(db_session, user_id, doc.id)
        assert found is not None
        assert found.id == doc.id

        not_found = await get_document(db_session, user_id, uuid.uuid4())
        assert not_found is None

    @pytest.mark.asyncio
    async def test_filter_by_status(self, db_session):
        user_id = uuid.uuid4()
        doc = await upload_document(
            db_session, user_id, b"test", "doc.pdf", "application/pdf"
        )

        # Default status is pending
        pending = await get_documents(db_session, user_id, status="pending")
        done = await get_documents(db_session, user_id, status="done")
        assert len(pending) == 1
        assert len(done) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_documents/ -v
```
Expected: ModuleNotFoundError

- [ ] **Step 3: Write schemas**

Create `backend/app/documents/schemas.py`:

```python
import uuid
import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field


class DocumentStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


class DocumentCreate(BaseModel):
    """Input: what the service layer creates."""
    pass  # creation is done by service, not by schema validation


class DocumentResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    original_name: str
    mime_type: str
    sha256_hash: str
    size_bytes: int
    status: str
    storage_path: str
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


class DocumentTextResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    extracted_text: str
    ocr_engine: Optional[str] = None
    extracted_at: Optional[dt.datetime] = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    document: DocumentResponse
    is_duplicate: bool = False
```

- [ ] **Step 4: Write service**

Create `backend/app/documents/service.py`:

```python
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
    """Compute SHA-256 hash of binary content."""
    return hashlib.sha256(content).hexdigest()


def _storage_path(sha256_hash: str) -> str:
    """Generate storage path: {first2}/{full_hash}"""
    return f"{sha256_hash[:2]}/{sha256_hash}"


def _ensure_storage_dir(sha256_hash: str):
    """Create storage directory if not exists."""
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
    """Upload a document. Deduplicates by SHA-256 hash."""
    sha256_hash = compute_sha256(content)

    # Check for duplicate
    existing = await db.execute(
        select(Document).where(
            Document.user_id == user_id,
            Document.sha256_hash == sha256_hash,
        )
    )
    existing_doc = existing.scalar_one_or_none()
    if existing_doc is not None:
        return existing_doc

    # Save to disk
    storage_dir = _ensure_storage_dir(sha256_hash)
    file_path = storage_dir / sha256_hash
    if not file_path.exists():
        file_path.write_bytes(content)

    # Create DB record
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


async def update_document_status(
    db: AsyncSession,
    document_id: uuid.UUID,
    status: str,
) -> Document | None:
    """Update document processing status."""
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        return None
    doc.status = status
    await db.flush()
    return doc


async def save_extracted_text(
    db: AsyncSession,
    document_id: uuid.UUID,
    text: str,
    ocr_engine: str = "stirling",
) -> DocumentText:
    """Save OCR-extracted text for a document."""
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
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> list[Document]:
    """List documents for a user, optionally filtered by status."""
    stmt = (
        select(Document)
        .where(Document.user_id == user_id)
        .order_by(Document.created_at.desc())
    )
    if status:
        stmt = stmt.where(Document.status == status)

    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_document(
    db: AsyncSession,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Document | None:
    """Get a single document by ID."""
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_document_text(
    db: AsyncSession,
    document_id: uuid.UUID,
) -> DocumentText | None:
    """Get extracted text for a document."""
    result = await db.execute(
        select(DocumentText).where(DocumentText.document_id == document_id)
    )
    return result.scalar_one_or_none()


async def delete_document(
    db: AsyncSession,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
) -> bool:
    """Delete a document (DB record only, not disk file)."""
    doc = await get_document(db, user_id, document_id)
    if doc is None:
        return False
    await db.delete(doc)
    await db.flush()
    return True
```

- [ ] **Step 5: Run tests**

```bash
cd backend && python -m pytest tests/test_documents/ -v
```
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/documents/service.py backend/app/documents/schemas.py backend/tests/test_documents/
git commit -m "feat: documents service — upload with SHA-256 dedup, list, get, delete"
```

---

### Task 3: Documents API router

**Files:**
- Modify: `backend/app/documents/router.py`
- Modify: `backend/app/documents/models.py` (add `status` column to Document)
- Create: `backend/tests/test_documents/test_router.py`

First, add `status` column to the Document model. Modify `backend/app/documents/models.py`:

```python
class Document(Base):
    __tablename__ = "documents"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(500))
    original_name: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    sha256_hash: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_path: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")

    text: Mapped[Optional["DocumentText"]] = relationship("DocumentText", back_populates="document", uselist=False, cascade="all, delete-orphan")
```

Also add `back_populates="document"` to `DocumentText.document` relationship.

Now create the migration and router.

- [ ] **Step 1: Generate migration for status column**

```bash
cd backend && python -m alembic revision --autogenerate -m "add_status_to_documents"
cd backend && python -m alembic upgrade head
```

- [ ] **Step 2: Rewrite router with full endpoints**

Replace `backend/app/documents/router.py`:

```python
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.identity.models import User
from app.identity.router import get_current_user
from app.documents import service
from app.documents.schemas import (
    DocumentResponse,
    DocumentTextResponse,
    DocumentUploadResponse,
)

router = APIRouter()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
}


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document for OCR processing."""
    if file.content_type not in ALLOWED_MIME_TYPES:
        return JSONResponse(
            content={"detail": f"Unsupported file type: {file.content_type}. Allowed: PDF, JPG, PNG."},
            status_code=400,
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        return JSONResponse(
            content={"detail": "File too large. Maximum size: 20 MB."},
            status_code=400,
        )

    doc = await service.upload_document(
        db, current_user.id, content, file.filename or "untitled", file.content_type or "application/octet-stream",
    )

    # Check if it was a duplicate
    is_duplicate = doc.created_at != doc.updated_at

    # Enqueue OCR job
    if not is_duplicate:
        from app.worker import enqueue_process_document
        await enqueue_process_document(str(doc.id))

    return DocumentUploadResponse(
        document=DocumentResponse.model_validate(doc),
        is_duplicate=is_duplicate,
    )


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, pattern=r"^(pending|processing|done|error)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's documents."""
    docs = await service.get_documents(db, current_user.id, limit=limit, offset=offset, status=status)
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get document metadata."""
    doc = await service.get_document(db, current_user.id, document_id)
    if doc is None:
        return JSONResponse(content={"detail": "Document not found"}, status_code=404)
    return DocumentResponse.model_validate(doc)


@router.get("/{document_id}/text", response_model=DocumentTextResponse)
async def get_document_text(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get extracted text for a document."""
    doc = await service.get_document(db, current_user.id, document_id)
    if doc is None:
        return JSONResponse(content={"detail": "Document not found"}, status_code=404)

    text = await service.get_document_text(db, document_id)
    if text is None:
        return JSONResponse(
            content={"detail": "Text not yet extracted or processing failed"},
            status_code=404,
        )
    return DocumentTextResponse.model_validate(text)


@router.delete("/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document."""
    deleted = await service.delete_document(db, current_user.id, document_id)
    if not deleted:
        return JSONResponse(content={"detail": "Document not found"}, status_code=404)
    return {"message": "Document deleted"}
```

- [ ] **Step 3: Write router test**

Create `backend/tests/test_documents/test_router.py`:

```python
import io
import uuid

import pytest
from httpx import AsyncClient


class TestDocumentsRouter:
    @pytest.mark.asyncio
    async def test_upload_requires_auth(self, async_client):
        response = await async_client.post(
            "/api/documents/upload",
            files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
        )
        # Without auth header
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_list_requires_auth(self, async_client):
        response = await async_client.get("/api/documents")
        assert response.status_code in (401, 403)
```

- [ ] **Step 4: Run all document tests**

```bash
cd backend && python -m pytest tests/test_documents/ -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/documents/router.py backend/app/documents/models.py backend/migrations/ backend/tests/test_documents/
git commit -m "feat: documents API — upload, list, get, delete, text endpoints"
```

---

### Task 4: ARQ worker + process_document task

**Files:**
- Create: `backend/app/worker.py`
- Create: `backend/tests/test_documents/test_worker.py`

- [ ] **Step 1: Write worker module**

Create `backend/app/worker.py`:

```python
"""ARQ worker for async document processing."""
import uuid
from datetime import datetime, timezone

import httpx
from arq import create_pool
from arq.connections import RedisSettings, ArqRedis

from app.config import settings
from app.database import async_session_factory
from app.documents import service
from app.documents.schemas import DocumentStatus


REDIS_SETTINGS = RedisSettings(host="redis", port=6379, database=1)

STIRLING_OCR_URL = f"{settings.STIRLING_PDF_URL}/api/v1/misc/ocr-pdf"
STIRLING_IMG_TO_PDF_URL = f"{settings.STIRLING_PDF_URL}/api/v1/convert/img/pdf"


async def enqueue_process_document(document_id: str):
    """Enqueue a document for OCR processing."""
    redis: ArqRedis = await create_pool(REDIS_SETTINGS)
    await redis.enqueue_job("process_document", document_id)
    await redis.close()


async def _convert_image_to_pdf(client: httpx.AsyncClient, file_path: str) -> bytes:
    """Convert JPG/PNG to PDF via Stirling."""
    with open(file_path, "rb") as f:
        files = {"fileInput": f}
        response = await client.post(STIRLING_IMG_TO_PDF_URL, files=files)
        response.raise_for_status()
        return response.content


async def _ocr_pdf(client: httpx.AsyncClient, file_path: str) -> str:
    """Run OCR on a PDF via Stirling, return extracted text."""
    with open(file_path, "rb") as f:
        files = {"fileInput": f}
        data = {
            "languages": "pol,eng",
            "ocrType": "skip-text",
            "sidecar": "true",
        }
        response = await client.post(STIRLING_OCR_URL, files=files, data=data)
        response.raise_for_status()
        return response.text


async def process_document(ctx, document_id: str) -> None:
    """Process a document: image→PDF → OCR → save text. Called by ARQ worker."""
    doc_id = uuid.UUID(document_id)
    upload_dir = service.UPLOAD_DIR

    async with async_session_factory() as db:
        from sqlalchemy import select
        from app.documents.models import Document
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()

        if doc is None:
            return

        # Update status to processing
        await service.update_document_status(db, doc_id, DocumentStatus.PROCESSING)
        await db.commit()

        try:
            file_path = upload_dir / doc.storage_path
            mime_type = doc.mime_type

            async with httpx.AsyncClient(timeout=120.0) as client:
                # If image, convert to PDF first
                if mime_type and mime_type.startswith("image/"):
                    pdf_content = await _convert_image_to_pdf(client, str(file_path))
                    # Save converted PDF temporarily
                    pdf_path = file_path.parent / f"{doc.sha256_hash}.pdf"
                    pdf_path.write_bytes(pdf_content)
                    ocr_file = str(pdf_path)
                else:
                    ocr_file = str(file_path)

                # Run OCR
                try:
                    text = await _ocr_pdf(client, ocr_file)
                except Exception:
                    text = await _ocr_pdf(client, ocr_file)

            # Save extracted text
            await service.save_extracted_text(db, doc_id, text, ocr_engine="stirling")
            await service.update_document_status(db, doc_id, DocumentStatus.DONE)
            await db.commit()

        except Exception as e:
            # Save error info
            await service.save_extracted_text(
                db, doc_id,
                f'{{"error": "{str(e)}"}}',
                ocr_engine="stirling",
            )
            await service.update_document_status(db, doc_id, DocumentStatus.ERROR)
            await db.commit()


class WorkerSettings:
    functions = [process_document]
    redis_settings = REDIS_SETTINGS
```

- [ ] **Step 2: Run document tests (no regressions)**

```bash
cd backend && python -m pytest tests/test_documents/ -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/worker.py
git commit -m "feat: ARQ worker — process_document task (image→PDF→OCR→text)"
```

---

### Task 5: Start worker and verify end-to-end

**Files:** None (verification only)

- [ ] **Step 1: Start the worker container**

```bash
cd /docker/finanse && docker compose up -d worker
```

- [ ] **Step 2: Test upload → OCR end-to-end**

```bash
# Create a simple test PDF
echo "%PDF-1.4 test content" > /tmp/test.pdf

# Upload via API (requires auth token first)
TOKEN=$(curl -s -c - http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.pl","password":"..."}' | grep advisor_session)

# Upload document
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@/tmp/test.pdf" \
  -b "advisor_session=$TOKEN"
# Expected: {"document": {...}, "is_duplicate": false}

# Check worker logs
docker logs finanse-worker
# Expected: "process_document" job completed

# Check document status
curl http://localhost:8000/api/documents \
  -b "advisor_session=$TOKEN"
# Expected: status "done" with created_at timestamp
```

- [ ] **Step 3: Commit verification (if changes needed)**

---

### Task 6: Frontend — API hooks

**Files:**
- Create: `frontend/src/api/documents.ts`

- [ ] **Step 1: Create API hooks**

Create `frontend/src/api/documents.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";

export interface DocumentData {
  id: string;
  user_id: string;
  filename: string;
  original_name: string;
  mime_type: string;
  sha256_hash: string;
  size_bytes: number;
  status: "pending" | "processing" | "done" | "error";
  storage_path: string;
  created_at: string;
  updated_at: string;
}

export interface DocumentText {
  id: string;
  document_id: string;
  extracted_text: string;
  ocr_engine: string | null;
  extracted_at: string | null;
  created_at: string;
}

export interface DocumentUploadResponse {
  document: DocumentData;
  is_duplicate: boolean;
}

export function useDocuments(params?: { status?: string }) {
  return useQuery({
    queryKey: ["documents", params],
    queryFn: async () => {
      const { data } = await api.get<DocumentData[]>("/documents", { params });
      return data;
    },
    // Auto-refresh if any document is processing
    refetchInterval: (query) => {
      const docs = query.state.data;
      if (docs?.some((d) => d.status === "processing" || d.status === "pending")) {
        return 3000; // poll every 3s
      }
      return false;
    },
  });
}

export function useDocument(id: string) {
  return useQuery({
    queryKey: ["documents", id],
    queryFn: async () => {
      const { data } = await api.get<DocumentData>(`/documents/${id}`);
      return data;
    },
    enabled: !!id,
  });
}

export function useDocumentText(id: string) {
  return useQuery({
    queryKey: ["documents", id, "text"],
    queryFn: async () => {
      const { data } = await api.get<DocumentText>(`/documents/${id}/text`);
      return data;
    },
    enabled: !!id,
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      const { data } = await api.post<DocumentUploadResponse>(
        "/documents/upload",
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
        }
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/documents/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const STATUS_LABELS: Record<string, string> = {
  pending: "Oczekuje",
  processing: "Przetwarzanie",
  done: "Gotowe",
  error: "Błąd",
};

export const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-600 text-gray-200",
  processing: "bg-yellow-600 text-yellow-100",
  done: "bg-green-600 text-green-100",
  error: "bg-red-600 text-red-100",
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/documents.ts
git commit -m "feat: documents API hooks — upload, list, text, delete"
```

---

### Task 7: Frontend — DocumentUpload component

**Files:**
- Create: `frontend/src/components/DocumentUpload.tsx`

- [ ] **Step 1: Create upload component**

Create `frontend/src/components/DocumentUpload.tsx`:

```tsx
import { useRef, useState, DragEvent, ChangeEvent } from "react";
import { useUploadDocument } from "../api/documents";

export function DocumentUpload() {
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadDocument();

  const handleFile = (file: File) => {
    upload.mutate(file);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = ""; // reset
  };

  return (
    <div className="mb-6">
      <div
        className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer ${
          dragActive
            ? "border-advisor-400 bg-advisor-400/10"
            : "border-gray-700 hover:border-gray-500 bg-gray-900"
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png"
          className="hidden"
          onChange={handleChange}
        />
        <input
          ref={cameraInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={handleChange}
        />
        <svg className="w-12 h-12 mx-auto mb-3 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
        </svg>
        <p className="text-gray-300 font-medium">
          Upuść dokument tutaj lub kliknij, aby wybrać
        </p>
        <p className="text-gray-500 text-sm mt-1">PDF, JPG, PNG — max 20 MB</p>
      </div>

      <div className="flex gap-3 mt-3">
        <button
          onClick={(e) => { e.stopPropagation(); cameraInputRef.current?.click(); }}
          className="flex-1 py-2 px-4 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 text-sm transition-colors flex items-center justify-center gap-2"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          Aparat
        </button>
      </div>

      {upload.isPending && (
        <div className="mt-2 text-sm text-yellow-400 flex items-center gap-2">
          <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
            <path fill="currentColor" className="opacity-75"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Przesyłanie...
        </div>
      )}

      {upload.isError && (
        <p className="mt-2 text-sm text-red-400">Błąd przesyłania. Spróbuj ponownie.</p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/DocumentUpload.tsx
git commit -m "feat: DocumentUpload component — drag & drop + camera capture"
```

---

### Task 8: Frontend — DocumentList + DocumentViewer components

**Files:**
- Create: `frontend/src/components/DocumentList.tsx`
- Create: `frontend/src/components/DocumentViewer.tsx`

- [ ] **Step 1: Create DocumentList**

Create `frontend/src/components/DocumentList.tsx`:

```tsx
import { useState } from "react";
import { useDocuments, useDeleteDocument, DocumentData, formatFileSize, STATUS_LABELS, STATUS_COLORS } from "../api/documents";
import { DocumentViewer } from "./DocumentViewer";

export function DocumentList() {
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [viewingDoc, setViewingDoc] = useState<DocumentData | null>(null);
  const { data: documents, isLoading } = useDocuments(
    statusFilter ? { status: statusFilter } : undefined
  );
  const deleteDoc = useDeleteDocument();

  if (isLoading) {
    return <p className="text-gray-400 text-sm">Ładowanie dokumentów...</p>;
  }

  if (!documents || documents.length === 0) {
    return (
      <p className="text-gray-500 text-sm py-8 text-center">
        Brak dokumentów. Upuść plik powyżej lub zrób zdjęcie.
      </p>
    );
  }

  return (
    <div>
      {/* Status filter */}
      <div className="flex gap-2 mb-4 flex-wrap">
        {[undefined, "pending", "processing", "done", "error"].map((s) => (
          <button
            key={s ?? "all"}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              statusFilter === s
                ? "bg-advisor-600 text-white"
                : "bg-gray-800 text-gray-400 hover:bg-gray-700"
            }`}
          >
            {s ? STATUS_LABELS[s] : "Wszystkie"}
          </button>
        ))}
      </div>

      {/* Document list */}
      <div className="space-y-2">
        {documents.map((doc) => (
          <div
            key={doc.id}
            className="flex items-center gap-4 p-3 bg-gray-900 rounded-lg hover:bg-gray-800 transition-colors cursor-pointer"
            onClick={() => setViewingDoc(doc)}
          >
            {/* File icon */}
            <div className="w-10 h-10 rounded-lg bg-gray-800 flex items-center justify-center flex-shrink-0">
              {doc.mime_type.startsWith("image/") ? (
                <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              ) : (
                <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              )}
            </div>

            {/* Doc info */}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-200 truncate">
                {doc.original_name}
              </p>
              <p className="text-xs text-gray-500">
                {formatFileSize(doc.size_bytes)} · {new Date(doc.created_at).toLocaleDateString("pl-PL")}
              </p>
            </div>

            {/* Status badge */}
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium flex-shrink-0 ${STATUS_COLORS[doc.status]}`}>
              {doc.status === "processing" && (
                <svg className="w-3 h-3 inline mr-1 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
                  <path fill="currentColor" className="opacity-75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              )}
              {STATUS_LABELS[doc.status]}
            </span>

            {/* Delete button */}
            <button
              onClick={(e) => { e.stopPropagation(); if (confirm("Usunąć dokument?")) deleteDoc.mutate(doc.id); }}
              className="p-1 text-gray-600 hover:text-red-400 transition-colors flex-shrink-0"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        ))}
      </div>

      {/* Viewer modal */}
      {viewingDoc && (
        <DocumentViewer document={viewingDoc} onClose={() => setViewingDoc(null)} />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create DocumentViewer**

Create `frontend/src/components/DocumentViewer.tsx`:

```tsx
import { useDocumentText, DocumentData, STATUS_LABELS, STATUS_COLORS, formatFileSize } from "../api/documents";

interface Props {
  document: DocumentData;
  onClose: () => void;
}

export function DocumentViewer({ document: doc, onClose }: Props) {
  const { data: textData, isLoading: textLoading } = useDocumentText(doc.id);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" onClick={onClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col m-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-800">
          <div>
            <h3 className="text-lg font-semibold text-white">{doc.original_name}</h3>
            <p className="text-sm text-gray-500">
              {formatFileSize(doc.size_bytes)} · {new Date(doc.created_at).toLocaleString("pl-PL")}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[doc.status]}`}>
              {STATUS_LABELS[doc.status]}
            </span>
            <button onClick={onClose} className="text-gray-400 hover:text-white">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {doc.status === "pending" || doc.status === "processing" ? (
            <div className="text-center py-8">
              <svg className="w-8 h-8 mx-auto mb-3 animate-spin text-advisor-400" fill="none" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
                <path fill="currentColor" className="opacity-75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <p className="text-gray-400">Dokument jest przetwarzany...</p>
            </div>
          ) : doc.status === "error" ? (
            <div className="text-center py-8">
              <p className="text-red-400">Błąd przetwarzania dokumentu.</p>
            </div>
          ) : textLoading ? (
            <p className="text-gray-400">Ładowanie tekstu...</p>
          ) : textData ? (
            <pre className="text-sm text-gray-300 whitespace-pre-wrap font-mono bg-gray-950 p-4 rounded-lg">
              {textData.extracted_text}
            </pre>
          ) : (
            <p className="text-gray-500">Brak wyekstrahowanego tekstu.</p>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DocumentList.tsx frontend/src/components/DocumentViewer.tsx
git commit -m "feat: DocumentList + DocumentViewer — status badges, text preview modal"
```

---

### Task 9: Frontend — Documents page + route + navigation

**Files:**
- Create: `frontend/src/pages/Documents.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout.tsx`

- [ ] **Step 1: Create Documents page**

Create `frontend/src/pages/Documents.tsx`:

```tsx
import { DocumentUpload } from "../components/DocumentUpload";
import { DocumentList } from "../components/DocumentList";

export function Documents() {
  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-6">Dokumenty</h1>
      <DocumentUpload />
      <DocumentList />
    </div>
  );
}
```

- [ ] **Step 2: Add route to App.tsx**

In `frontend/src/App.tsx`, add:
```tsx
import { Documents } from "./pages/Documents";
```

And add route:
```tsx
<Route path="/documents" element={<Documents />} />
```

- [ ] **Step 3: Add navigation link to Layout**

In `frontend/src/components/Layout.tsx`, add to `navItems`:
```tsx
{ to: "/documents", label: "Dokumenty", icon: DocumentIcon },
```

Add the icon at the bottom:
```tsx
function DocumentIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Documents.tsx frontend/src/App.tsx frontend/src/components/Layout.tsx
git commit -m "feat: Documents page with route and navigation link"
```

---

### Task 10: Production deployment + verification

**Files:** None (operational)

- [ ] **Step 1: Rebuild and restart all services**

```bash
cd /docker/finanse
docker compose build backend frontend worker
docker compose up -d
```

- [ ] **Step 2: Verify Stirling PDF**

```bash
curl http://localhost:8080/api/v1/info/status
# Expected: {"version": "..."}
```

- [ ] **Step 3: Verify worker**

```bash
docker logs finanse-worker
# Expected: arq worker started, no errors
```

- [ ] **Step 4: Test end-to-end upload**

Upload a test document through the UI or curl, check that OCR text appears in the viewer.

- [ ] **Step 5: Push to git**

```bash
git push
```

- [ ] **Step 6: Update CHANGELOG and TASKS**

---
