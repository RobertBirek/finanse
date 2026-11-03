"""Archival is reversible visibility, never deletion of evidence or finance sources."""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.audit.models import AuditEvent
from app.documents import service
from app.documents.job_models import DocumentProcessingJob
from app.documents.models import Document, DocumentExtractionRevision, DocumentText
from app.finance.models import FinancialDocument, FinancialDocumentSource
from app.identity.models import User
from app.identity.router import get_current_user
from app.main import app

pytestmark = pytest.mark.integration


async def make_document(db, **values):
    doc = Document(
        user_id=uuid.uuid4(),
        filename="synthetic",
        original_name="synthetic",
        mime_type="image/jpeg",
        sha256_hash=uuid.uuid4().hex * 2,
        size_bytes=1,
        storage_path="synthetic",
        status="done",
        processing_method="vision",
    )
    for name, value in values.items():
        setattr(doc, name, value)
    if await db.get(User, doc.user_id) is None:
        db.add(
            User(
                id=doc.user_id,
                email=f"{doc.user_id}@example.test",
                password_hash="synthetic",
                display_name="Synthetic",
            )
        )
        await db.flush()
    db.add(doc)
    await db.flush()
    return doc


async def make_revision(db, doc, *, status="ready", method="image", number=1):
    revision = DocumentExtractionRevision(
        user_id=doc.user_id,
        document_id=doc.id,
        revision=number,
        status=status,
        input_method=method,
        data={"document_type": "other", "fields": {}},
        field_provenance={},
    )
    db.add(revision)
    await db.flush()
    return revision


async def make_job(db, doc, *, state="succeeded", revision=None):
    job = DocumentProcessingJob(
        user_id=doc.user_id,
        document_id=doc.id,
        revision_id=revision.id if revision else None,
        kind="vision" if revision else "local_ocr",
        state=state,
        intent_key=str(uuid.uuid4()),
        request_hash="synthetic",
    )
    db.add(job)
    await db.flush()
    return job


def authenticate(owner):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=owner)


@pytest.mark.parametrize("history", ["none", "text", "review", "vision", "ocr"])
async def test_legacy_delete_archives_without_removing_evidence(
    db_session, async_client, tmp_path, history
):
    original = tmp_path / "original"
    original.write_bytes(b"synthetic")
    doc = await make_document(db_session, storage_path=str(original))
    if history == "text":
        db_session.add(DocumentText(document_id=doc.id, extracted_text="synthetic"))
    if history in {"review", "vision"}:
        rev = await make_revision(db_session, doc)
        if history == "vision":
            await make_job(db_session, doc, revision=rev)
    if history == "ocr":
        await make_job(db_session, doc)
    await db_session.flush()
    authenticate(doc.user_id)
    before = {
        model.__tablename__: await db_session.scalar(select(func.count()).select_from(model))
        for model in (Document, DocumentText, DocumentExtractionRevision, DocumentProcessingJob)
    }
    response = await async_client.delete(f"/api/documents/{doc.id}")
    assert response.status_code == 200
    assert response.json() == {"message": "Document archived"}
    await db_session.refresh(doc)
    assert doc.archived_at is not None
    assert original.read_bytes() == b"synthetic"
    for model in (Document, DocumentText, DocumentExtractionRevision, DocumentProcessingJob):
        assert (
            await db_session.scalar(select(func.count()).select_from(model))
            == before[model.__tablename__]
        )


async def test_archive_restore_idempotent_and_owner_scoped(db_session, async_client):
    doc = await make_document(db_session)
    authenticate(doc.user_id)
    response = await async_client.post(f"/api/documents/{doc.id}/archive")
    assert response.status_code == 200
    archived_at = response.json()["archived_at"]
    repeated = await async_client.post(f"/api/documents/{doc.id}/archive")
    assert repeated.json()["archived_at"] == archived_at
    assert (await async_client.get("/api/documents")).json() == []
    assert [
        row["id"] for row in (await async_client.get("/api/documents?archived=true")).json()
    ] == [str(doc.id)]
    assert (await async_client.get(f"/api/documents/{doc.id}")).json()["archived_at"] == archived_at
    assert (await async_client.get("/api/documents/active")).json() == []
    for _ in range(2):
        restored = await async_client.post(f"/api/documents/{doc.id}/restore")
        assert restored.status_code == 200 and restored.json()["archived_at"] is None
    actions = list(
        (
            await db_session.execute(
                select(AuditEvent.action)
                .where(AuditEvent.entity_type == "document", AuditEvent.entity_id == str(doc.id))
                .order_by(AuditEvent.created_at)
            )
        ).scalars()
    )
    assert actions == ["archived", "restored"]
    authenticate(uuid.uuid4())
    for action in ("archive", "restore"):
        foreign = await async_client.post(f"/api/documents/{doc.id}/{action}")
        missing = await async_client.post(f"/api/documents/{uuid.uuid4()}/{action}")
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json()["code"] == missing.json()["code"] == "document_not_found"


async def test_approved_finance_source_remains_unchanged_and_readable(
    db_session, async_client, tmp_path, monkeypatch
):
    original = tmp_path / "synthetic"
    original.write_bytes(b"synthetic")
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    doc = await make_document(db_session, sha256_hash=service.compute_sha256(b"synthetic"))
    finance = FinancialDocument(
        user_id=doc.user_id,
        kind="invoice",
        supplier_name="Synthetic",
        description="Synthetic",
        total_minor=100,
        currency="PLN",
        review="approved",
    )
    db_session.add(finance)
    await db_session.flush()
    source = FinancialDocumentSource(
        user_id=doc.user_id, financial_document_id=finance.id, document_id=doc.id
    )
    db_session.add(source)
    await db_session.flush()
    expected = (
        finance.version,
        finance.review,
        finance.lifecycle,
        finance.total_minor,
        source.document_id,
    )
    authenticate(doc.user_id)
    assert (await async_client.post(f"/api/documents/{doc.id}/archive")).status_code == 200
    assert (await async_client.get(f"/api/documents/{doc.id}/original")).content == b"synthetic"
    await db_session.refresh(finance)
    await db_session.refresh(source)
    assert (
        finance.version,
        finance.review,
        finance.lifecycle,
        finance.total_minor,
        source.document_id,
    ) == expected
