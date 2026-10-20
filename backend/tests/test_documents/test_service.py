import asyncio
import fcntl
import hashlib
import uuid
from pathlib import Path

import pytest

from app.documents import service
from app.documents.service import compute_sha256, get_document, get_documents, upload_document


@pytest.fixture(autouse=True)
def isolated_upload_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)


class TestComputeSha256:
    def test_computes_hash(self):
        content = b"hello world"
        expected = hashlib.sha256(content).hexdigest()
        result = compute_sha256(content)
        assert result == expected
        assert len(result) == 64

    def test_different_content_different_hash(self):
        assert compute_sha256(b"a") != compute_sha256(b"b")


@pytest.mark.asyncio
async def test_upload_waits_for_backup_lock_without_blocking_event_loop(
    tmp_path: Path, monkeypatch
):
    class Result:
        def scalar_one_or_none(self):
            return None

    class Database:
        flushed = False

        async def execute(self, _statement):
            return Result()

        def add(self, _document):
            pass

        async def flush(self):
            self.flushed = True

    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    lock_path = tmp_path / ".backup.lock"
    lock_path.touch()
    lock_file = lock_path.open("a+b")
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
    database = Database()
    upload_task = asyncio.create_task(
        upload_document(database, uuid.uuid4(), b"locked content", "test.pdf", "application/pdf")
    )
    await asyncio.sleep(0.05)
    ticker_ran = False

    async def tick():
        nonlocal ticker_ran
        await asyncio.sleep(0)
        ticker_ran = True

    await tick()
    assert ticker_ran
    assert not database.flushed
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    lock_file.close()
    document = await upload_task
    assert (tmp_path / document.storage_path).read_bytes() == b"locked content"
    assert database.flushed


class TestAtomicStorage:
    def test_publishes_only_fully_written_content(self, tmp_path, monkeypatch):
        content = b"complete original"
        digest = compute_sha256(content)
        target = tmp_path / digest[:2] / digest
        original_link = service.os.link

        def link(source, destination):
            assert not target.exists()
            assert Path(source).read_bytes() == content
            original_link(source, destination)

        monkeypatch.setattr(service.os, "link", link)
        service._write_document_content(digest, content)
        assert target.read_bytes() == content
        assert not list(target.parent.glob(".upload-*"))

    def test_interrupted_write_never_leaves_a_partial_original(self, tmp_path, monkeypatch):
        content = b"original"
        digest = compute_sha256(content)

        def fail(_descriptor):
            raise OSError("simulated disk failure")

        monkeypatch.setattr(service.os, "fsync", fail)
        with pytest.raises(OSError):
            service._write_document_content(digest, content)
        assert not (tmp_path / digest[:2] / digest).exists()
        assert not list((tmp_path / digest[:2]).glob(".upload-*"))

    def test_duplicate_does_not_replace_original_inode(self, tmp_path):
        content = b"original"
        digest = compute_sha256(content)
        service._write_document_content(digest, content)
        target = tmp_path / digest[:2] / digest
        inode = target.stat().st_ino
        service._write_document_content(digest, content)
        assert target.stat().st_ino == inode
        assert target.read_bytes() == content

    def test_corrupt_existing_file_is_detected_and_never_overwritten(self, tmp_path):
        digest = compute_sha256(b"original")
        directory = tmp_path / digest[:2]
        directory.mkdir()
        target = directory / digest
        target.write_bytes(b"partial")
        with pytest.raises(OSError, match="integrity"):
            service._write_document_content(digest, b"original")
        assert target.read_bytes() == b"partial"

    @pytest.mark.asyncio
    async def test_storage_failure_is_a_safe_503_and_never_enqueued(self, monkeypatch):
        import io
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from fastapi import UploadFile
        from starlette.datastructures import Headers

        from app.documents import router

        monkeypatch.setattr(
            service, "store_document", AsyncMock(side_effect=OSError("private-path-secret"))
        )
        file = UploadFile(
            io.BytesIO(b"original"),
            filename="test.pdf",
            headers=Headers({"content-type": "application/pdf"}),
        )
        response = await router.upload_document(file, SimpleNamespace(id=uuid.uuid4()), None, None)
        assert response.status_code == 503
        assert b"private-path-secret" not in response.body


class TestDocumentService:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_upload_creates_document(self, db_session):
        user_id = uuid.uuid4()
        doc = await upload_document(
            db_session, user_id, b"%PDF-1.4 test", "test.pdf", "application/pdf"
        )
        assert doc.id is not None
        assert doc.original_name == "test.pdf"
        assert doc.mime_type == "application/pdf"
        assert doc.size_bytes == 13
        assert doc.status == "pending"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_upload_deduplicates_same_hash(self, db_session):
        user_id = uuid.uuid4()
        content = b"same content"
        doc1 = await upload_document(db_session, user_id, content, "a.pdf", "application/pdf")
        doc2 = await upload_document(db_session, user_id, content, "b.pdf", "application/pdf")
        assert doc1.id == doc2.id

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_list_returns_by_user(self, db_session):
        a, b = uuid.uuid4(), uuid.uuid4()
        await upload_document(db_session, a, b"a", "a.pdf", "application/pdf")
        await upload_document(db_session, b, b"b", "b.pdf", "application/pdf")
        assert len(await get_documents(db_session, a)) == 1
        assert len(await get_documents(db_session, b)) == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_document_by_id(self, db_session):
        user_id = uuid.uuid4()
        doc = await upload_document(db_session, user_id, b"test", "doc.pdf", "application/pdf")
        found = await get_document(db_session, user_id, doc.id)
        assert found is not None and found.id == doc.id
        assert await get_document(db_session, user_id, uuid.uuid4()) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_explicit_deduplication_and_text_upsert(db_session):
    from sqlalchemy import func, select

    from app.documents.models import DocumentText

    user = uuid.uuid4()
    document, duplicate = await service.store_document(
        db_session, user, b"same", "a.pdf", "application/pdf"
    )
    assert not duplicate
    same, duplicate = await service.store_document(
        db_session, user, b"same", "b.pdf", "application/pdf"
    )
    assert same.id == document.id and duplicate
    await service.save_extracted_text(db_session, document.id, "first")
    await service.save_extracted_text(db_session, document.id, "retry")
    assert await db_session.scalar(select(func.count()).select_from(DocumentText)) == 1
    assert (await service.get_document_text(db_session, document.id)).extracted_text == "retry"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upload_commits_before_enqueue_and_survives_redis_outage(
    db_session, async_client, monkeypatch
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app import worker
    from app.identity.router import get_current_user
    from app.main import app

    user = uuid.uuid4()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user)

    async def enqueue(document_id):
        async with async_sessionmaker(db_session.bind)() as other_session:
            assert (
                await service.get_document(other_session, user, uuid.UUID(document_id)) is not None
            )
        raise OSError("Redis unavailable")

    mock = AsyncMock(side_effect=enqueue)
    monkeypatch.setattr(worker, "enqueue_process_document", mock)
    response = await async_client.post(
        "/api/documents/upload",
        files={"file": ("receipt.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_duplicate"] is False
    assert body["document"]["status"] == "pending"
    assert mock.await_count == 1
    duplicate = await async_client.post(
        "/api/documents/upload",
        files={"file": ("receipt.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert duplicate.json()["is_duplicate"] is True

    document = await service.get_document(db_session, user, uuid.UUID(body["document"]["id"]))
    document.status = "error"
    await db_session.commit()
    retry = await async_client.post(
        "/api/documents/upload",
        files={"file": ("receipt.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert retry.status_code == 200
    assert retry.json()["is_duplicate"] is True
    assert retry.json()["document"]["status"] == "pending"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("extraction_failure", [False, True, "empty"])
async def test_image_worker_uses_pdf_bytes_and_is_idempotent(
    db_session, monkeypatch, extraction_failure
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app import worker
    from app.documents import extractor
    from app.documents.schemas import DocumentStatus
    from app.inbox.service import get_inbox_items

    document = await service.upload_document(
        db_session, uuid.uuid4(), b"original image", "receipt.png", "image/png"
    )
    document_id, user_id = document.id, document.user_id
    await db_session.commit()
    monkeypatch.setattr(
        worker, "async_session_factory", async_sessionmaker(db_session.bind, expire_on_commit=False)
    )
    convert = AsyncMock(return_value=b"converted PDF")
    ocr = AsyncMock(return_value=b"searchable PDF")
    monkeypatch.setattr(worker, "_convert_image_to_pdf", convert)
    monkeypatch.setattr(worker, "_ocr_pdf", ocr)
    monkeypatch.setattr(
        worker,
        "_pdf_to_text",
        AsyncMock(return_value="\n" if extraction_failure == "empty" else "Receipt text"),
    )
    extraction = AsyncMock(return_value={"detected": True, "amount": 100, "description": "Test"})
    if extraction_failure:
        extraction.side_effect = ValueError("Invalid model response")
    monkeypatch.setattr(extractor, "extract_financial_data", extraction)
    await worker.process_document({}, str(document_id))
    await worker.process_document({}, str(document_id))
    assert convert.await_count == ocr.await_count == 1
    assert ocr.await_args.args[2] == b"converted PDF"
    db_session.expire_all()
    persisted = await service.get_document(db_session, user_id, document_id)
    assert persisted.status == DocumentStatus.DONE
    assert (service.UPLOAD_DIR / persisted.storage_path).read_bytes() == b"original image"
    assert (await service.get_document_text(db_session, document_id)).extracted_text == (
        "\n" if extraction_failure == "empty" else "Receipt text"
    )
    if extraction_failure == "empty":
        extraction.assert_not_awaited()
    assert len(await get_inbox_items(db_session, user_id)) == (0 if extraction_failure else 1)
    redis = SimpleNamespace(enqueue_job=AsyncMock())
    pending = await service.upload_document(
        db_session, user_id, b"pending", "next.pdf", "application/pdf"
    )
    pending_id = pending.id
    await db_session.commit()
    await worker.dispatch_pending_documents({"redis": redis})
    redis.enqueue_job.assert_awaited_once_with(
        "process_document", str(pending_id), _job_id=f"document:{pending_id}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_recovers_only_stale_unlocked_documents_and_commits_before_queue_failure(
    db_session, monkeypatch
):
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app import worker
    from app.documents.models import Document

    user = uuid.uuid4()
    docs = [
        await service.upload_document(db_session, user, bytes([i]), f"{i}.pdf", "application/pdf")
        for i in range(3)
    ]
    ids = [doc.id for doc in docs]
    for doc in docs:
        doc.status = "processing"
    await db_session.flush()
    await db_session.execute(
        update(Document)
        .where(Document.id.in_([ids[0], ids[2]]))
        .values(updated_at=datetime.now(UTC) - timedelta(days=70))
    )
    await db_session.commit()
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(worker, "async_session_factory", factory)
    redis = SimpleNamespace(enqueue_job=AsyncMock(side_effect=OSError("offline")))
    async with factory() as active:
        await active.execute(select(Document).where(Document.id == ids[2]).with_for_update())
        with pytest.raises(OSError):
            await worker.dispatch_pending_documents({"redis": redis})
        db_session.expire_all()
        assert (await db_session.get(Document, ids[0])).status == "pending"
        assert (await db_session.get(Document, ids[1])).status == "processing"
        assert (await db_session.get(Document, ids[2])).status == "processing"
        await active.rollback()
    await db_session.rollback()
    redis.enqueue_job = AsyncMock()
    await worker.dispatch_pending_documents({"redis": redis})
    assert redis.enqueue_job.await_count == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recovered_document_does_not_duplicate_existing_inbox_suggestion(db_session):
    from app.documents.extractor import create_inbox_from_document
    from app.inbox.service import get_inbox_items

    user = uuid.uuid4()
    document = await service.upload_document(
        db_session, user, b"recovered", "test.pdf", "application/pdf"
    )
    first = await create_inbox_from_document(
        db_session, user, document.id, "test.pdf", {"amount": 100}
    )
    second = await create_inbox_from_document(
        db_session, user, document.id, "test.pdf", {"amount": 100}
    )
    assert first.id == second.id
    assert len(await get_inbox_items(db_session, user)) == 1
