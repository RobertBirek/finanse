import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import worker
from app.documents import service
from app.documents.models import Document
from test_documents.fixtures import valid_pdf_bytes


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["transient", "integrity", "oversize", "permanent"])
async def test_ocr_failure_classification_and_retry_budget(
    test_database, tmp_path, monkeypatch, failure
):
    from app.documents.ocr_client import OCRResponseTooLargeError

    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(worker, "async_session_factory", sessions)
    async with sessions() as db:
        doc, _ = await service.store_document(
            db, uuid.uuid4(), valid_pdf_bytes(), "a.pdf", "application/pdf"
        )
        await db.commit()
        doc_id = doc.id
        path = tmp_path / doc.storage_path
    error = httpx.HTTPStatusError(
        "unavailable",
        request=httpx.Request("POST", "http://ocr"),
        response=httpx.Response(503 if failure == "transient" else 400),
    )
    if failure == "oversize":
        error = OCRResponseTooLargeError()
    if failure == "integrity":
        path.write_bytes(b"changed")
    ocr = AsyncMock(side_effect=error)
    monkeypatch.setattr(worker, "_ocr_pdf", ocr)
    for attempt in range(1, 4 if failure == "transient" else 2):
        await worker.process_document({}, str(doc_id))
        async with sessions() as db:
            doc = await db.get(Document, doc_id)
            assert doc.attempt_count == attempt
            if failure == "transient" and attempt < 3:
                assert doc.status == "pending"
                assert doc.next_attempt_at > datetime.now(UTC)
                await worker.process_document({}, str(doc_id))  # early duplicate must not run
                assert ocr.await_count == attempt
                doc.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
                await db.commit()
            else:
                assert doc.status == "error"
                assert doc.next_attempt_at is None
    before = ocr.await_count
    await worker.process_document({}, str(doc_id))
    assert ocr.await_count == before
    if failure == "integrity":
        assert before == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retry_success_after_dispatcher_restart(test_database, tmp_path, monkeypatch):
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(worker, "async_session_factory", sessions)
    async with sessions() as db:
        doc, _ = await service.store_document(
            db, uuid.uuid4(), valid_pdf_bytes(), "a.pdf", "application/pdf"
        )
        await db.commit()
        doc_id = doc.id
    ocr = AsyncMock(side_effect=httpx.ConnectError("offline"))
    monkeypatch.setattr(worker, "_ocr_pdf", ocr)
    await worker.process_document({}, str(doc_id))
    queue = AsyncMock()
    await worker.dispatch_pending_documents({"redis": queue})
    queue.enqueue_job.assert_not_awaited()
    async with sessions() as db:
        doc = await db.get(Document, doc_id)
        doc.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    await worker.dispatch_pending_documents({"redis": queue})
    assert queue.enqueue_job.await_args.args == ("process_document", str(doc_id))
    monkeypatch.setattr(worker, "_ocr_pdf", AsyncMock(return_value=b"pdf"))
    monkeypatch.setattr(worker, "_pdf_to_text", AsyncMock(return_value=""))
    await worker.process_document({}, str(doc_id))
    async with sessions() as db:
        doc = await db.get(Document, doc_id)
        assert (doc.status, doc.attempt_count, doc.next_attempt_at, doc.last_error_code) == (
            "done",
            2,
            None,
            None,
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_savepoint_keeps_claim_after_database_write_failure(
    test_database, tmp_path, monkeypatch
):
    from sqlalchemy import text

    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(worker, "async_session_factory", sessions)
    async with sessions() as db:
        doc, _ = await service.store_document(
            db, uuid.uuid4(), valid_pdf_bytes(), "a.pdf", "application/pdf"
        )
        await db.commit()
        doc_id = doc.id

    async def fail_write(db, *args, **kwargs):
        await db.execute(text("SELECT 1 / 0"))

    monkeypatch.setattr(worker, "_ocr_pdf", AsyncMock(return_value=b"pdf"))
    monkeypatch.setattr(worker, "_pdf_to_text", AsyncMock(return_value=""))
    monkeypatch.setattr(service, "save_extracted_text", fail_write)
    await worker.process_document({}, str(doc_id))
    async with sessions() as db:
        doc = await db.get(Document, doc_id)
        assert (doc.status, doc.attempt_count, doc.last_error_code) == (
            "error",
            1,
            "processing_failed",
        )
