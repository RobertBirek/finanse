import uuid
from types import SimpleNamespace

import pytest

from test_documents.fixtures import valid_pdf_bytes


@pytest.mark.asyncio
async def test_chunked_multipart_over_limit_returns_413_not_parse_error():
    import httpx
    from fastapi import FastAPI, File, UploadFile

    from app.documents.upload_limits import DocumentUploadBodyLimitMiddleware

    app = FastAPI()
    app.add_middleware(DocumentUploadBodyLimitMiddleware, max_bytes=200)

    @app.post("/api/documents/upload")
    async def upload(file: UploadFile = File(...)):  # noqa: B008 - local test route
        raise AssertionError("oversized body reached handler")

    async def chunks():
        yield b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n'
        yield b"x" * 300
        yield b"\r\n--boundary--\r\n"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/documents/upload",
            content=chunks(),
            headers={"Content-Type": "multipart/form-data; boundary=boundary"},
        )
    assert response.status_code == 413


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers", [[], [(b"content-length", b"100")], [(b"content-length", b"2")]]
)
async def test_body_limit_rejects_before_forwarding_excess_chunk(headers):
    from app.documents.upload_limits import DocumentUploadBodyLimitMiddleware

    messages = iter(
        [
            {"type": "http.request", "body": b"ab", "more_body": True},
            {"type": "http.request", "body": b"cdef", "more_body": False},
        ]
    )
    sent, seen = [], []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    async def app(scope, receive, send):
        while True:
            msg = await receive()
            seen.append(msg["body"])
            if not msg["more_body"]:
                break

    middleware = DocumentUploadBodyLimitMiddleware(app, max_bytes=4)
    await middleware(
        {"type": "http", "method": "POST", "path": "/api/documents/upload", "headers": headers},
        receive,
        send,
    )
    assert sent[0]["status"] == 413
    assert b"cdef" not in seen


@pytest.mark.asyncio
async def test_body_limit_allows_exact_limit():
    from app.documents.upload_limits import DocumentUploadBodyLimitMiddleware

    async def app(scope, receive, send):
        assert (await receive())["body"] == b"abcd"
        await send({"type": "http.response.start", "status": 204, "headers": []})

    async def receive():
        return {"type": "http.request", "body": b"abcd", "more_body": False}

    sent = []

    async def send(message):
        sent.append(message)

    await DocumentUploadBodyLimitMiddleware(app, max_bytes=4)(
        {"type": "http", "method": "POST", "path": "/api/documents/upload", "headers": []},
        receive,
        send,
    )
    assert sent[0]["status"] == 204


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quota_rejects_new_document_but_allows_duplicate(db_session, monkeypatch, tmp_path):
    from app.config import settings
    from app.documents import service
    from app.documents.upload_limits import StorageQuotaExceededError

    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(settings, "DOCUMENT_MIN_FREE_BYTES", 1)
    content = valid_pdf_bytes()
    monkeypatch.setattr(settings, "DOCUMENT_USER_QUOTA_BYTES", len(content))
    user = uuid.uuid4()
    first, _ = await service.store_document(db_session, user, content, "a.pdf", "application/pdf")
    again, duplicate = await service.store_document(
        db_session, user, content, "b.pdf", "application/pdf"
    )
    assert again.id == first.id and duplicate
    with pytest.raises(StorageQuotaExceededError):
        await service.store_document(
            db_session, user, valid_pdf_bytes("other"), "c.pdf", "application/pdf"
        )
    assert len([p for p in tmp_path.rglob("*") if p.is_file() and not p.name.startswith(".")]) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_global_quota_and_disk_reserve_prevent_blob_write(db_session, monkeypatch, tmp_path):
    from app.config import settings
    from app.documents import service, upload_limits

    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(settings, "DOCUMENT_GLOBAL_QUOTA_BYTES", 1)
    with pytest.raises(upload_limits.StorageQuotaExceededError):
        await service.store_document(
            db_session, uuid.uuid4(), valid_pdf_bytes(), "a.pdf", "application/pdf"
        )
    monkeypatch.setattr(settings, "DOCUMENT_GLOBAL_QUOTA_BYTES", 100000)
    monkeypatch.setattr(upload_limits.shutil, "disk_usage", lambda _: SimpleNamespace(free=1))
    with pytest.raises(upload_limits.DocumentStorageFullError):
        await service.store_document(
            db_session, uuid.uuid4(), valid_pdf_bytes(), "a.pdf", "application/pdf"
        )
    assert not list(tmp_path.rglob("*"))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_users_cannot_exceed_global_quota(test_database, monkeypatch, tmp_path):
    import asyncio

    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.config import settings
    from app.documents import service, upload_limits
    from app.documents.models import Document

    content = valid_pdf_bytes()
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(settings, "DOCUMENT_GLOBAL_QUOTA_BYTES", len(content))
    monkeypatch.setattr(settings, "DOCUMENT_MIN_FREE_BYTES", 1)
    sessions = async_sessionmaker(test_database)

    async def upload():
        async with sessions() as db:
            try:
                await service.store_document(db, uuid.uuid4(), content, "a.pdf", "application/pdf")
                await db.commit()
                return "stored"
            except upload_limits.StorageQuotaExceededError:
                await db.rollback()
                return "quota"

    assert sorted(await asyncio.gather(upload(), upload())) == ["quota", "stored"]
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Document)) == 1
