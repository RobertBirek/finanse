import hashlib
import uuid
from io import BytesIO
from types import SimpleNamespace

import pytest

from test_documents.fixtures import valid_heic_bytes, valid_pdf_bytes


@pytest.mark.asyncio
@pytest.mark.integration
async def test_heic_original_unchanged_and_preview_jpeg(
    async_client, db_session, monkeypatch, tmp_path
):
    from app.documents import service
    from app.identity.router import get_current_user
    from app.main import app

    owner = uuid.uuid4()
    content = valid_heic_bytes()
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=owner)
    try:
        document = await service.upload_document(db_session, owner, content, "blob", "image/heic")
        await db_session.commit()
        original = await async_client.get(f"/api/documents/{document.id}/original")
        preview = await async_client.get(f"/api/documents/{document.id}/preview")
    finally:
        app.dependency_overrides.clear()

    assert hashlib.sha256(original.content).digest() == hashlib.sha256(content).digest()
    assert original.headers["content-disposition"].startswith("attachment;")
    assert original.headers["cache-control"] == "no-store"
    assert preview.content.startswith(b"\xff\xd8")
    assert preview.headers["cache-control"] == "no-store"
    assert preview.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("declared_mime", [None, "application/octet-stream"])
async def test_phone_generic_mime_is_detected_by_upload_endpoint(
    async_client, db_session, monkeypatch, tmp_path, declared_mime
):
    from app.documents import service
    from app.identity.router import get_current_user
    from app.main import app

    boundary = "phone-upload-boundary"
    headers = [b'Content-Disposition: form-data; name="file"; filename="blob"']
    if declared_mime is not None:
        headers.append(f"Content-Type: {declared_mime}".encode())
    content = valid_heic_bytes()
    body = b"\r\n".join(
        [
            f"--{boundary}".encode(),
            *headers,
            b"",
            content,
            f"--{boundary}--\r\n".encode(),
        ]
    )
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    try:
        response = await async_client.post(
            "/api/documents/upload",
            content=body,
            headers={"content-type": f"multipart/form-data; boundary={boundary}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["document"]["mime_type"] == "image/heif"


@pytest.mark.asyncio
async def test_malformed_heic_is_rejected_without_storage(tmp_path, monkeypatch):
    from fastapi import UploadFile
    from starlette.datastructures import Headers

    from app.documents import router, service

    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    response = await router.upload_document(
        UploadFile(
            BytesIO(b"not a HEIC"), filename="blob", headers=Headers({"content-type": "image/heic"})
        ),
        SimpleNamespace(id=uuid.uuid4()),
        None,
        None,
    )

    assert response.status_code == 400
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
@pytest.mark.integration
async def test_foreign_owner_cannot_read_original(async_client, db_session, monkeypatch, tmp_path):
    from app.documents import service
    from app.identity.router import get_current_user
    from app.main import app

    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    document = await service.upload_document(
        db_session, uuid.uuid4(), valid_pdf_bytes(), "receipt.pdf", "application/pdf"
    )
    await db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    try:
        response = await async_client.get(f"/api/documents/{document.id}/original")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "storage_path" not in response.text
