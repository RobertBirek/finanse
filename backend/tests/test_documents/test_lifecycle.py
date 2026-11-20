"""Archival is reversible visibility, never deletion of evidence or finance sources."""

import uuid
from datetime import UTC, datetime, timedelta
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


async def make_revision(db, doc, *, status="ready", method="image", number=1, kind="other"):
    revision = DocumentExtractionRevision(
        user_id=doc.user_id,
        document_id=doc.id,
        revision=number,
        status=status,
        input_method=method,
        data={"document_type": kind, "fields": {}},
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


async def test_worklist_counts_and_filtered_lists_share_document_state(db_session, async_client):
    ready = await make_document(db_session)
    await make_revision(db_session, ready, kind="invoice")
    failed = await make_document(db_session, user_id=ready.user_id)
    await make_revision(db_session, failed, kind="receipt")
    await make_revision(db_session, failed, kind="receipt", status="incomplete", number=2)
    pending = await make_document(db_session, user_id=ready.user_id)
    await make_revision(db_session, pending, kind="invoice")
    await make_job(db_session, pending, state="processing")
    unsupported = await make_document(db_session, user_id=ready.user_id)
    await make_revision(db_session, unsupported, kind="statement", status="incomplete")
    archived = await make_document(db_session, user_id=ready.user_id, archived_at=datetime.now(UTC))
    await make_revision(db_session, archived, kind="invoice")
    imported = await make_document(
        db_session, user_id=ready.user_id, processing_method="bank_import"
    )
    await make_revision(db_session, imported, kind="receipt")
    foreign = await make_document(db_session)
    await make_revision(db_session, foreign, kind="invoice")
    approved = await make_document(db_session, user_id=ready.user_id)
    await make_revision(db_session, approved, kind="invoice")
    bill = FinancialDocument(
        user_id=ready.user_id,
        kind="invoice",
        supplier_name="Test",
        description="Test",
        total_minor=1,
        currency="PLN",
        review="approved",
    )
    db_session.add(bill)
    await db_session.flush()
    db_session.add(
        FinancialDocumentSource(
            user_id=ready.user_id, document_id=approved.id, financial_document_id=bill.id
        )
    )
    await db_session.flush()

    authenticate(ready.user_id)
    counts = await async_client.get("/api/documents/worklists")
    assert counts.status_code == 200
    assert counts.json() == {"review": 1, "errors": 1}
    for kind, doc in [("review", ready), ("errors", failed)]:
        response = await async_client.get("/api/documents", params={"worklist": kind})
        assert response.status_code == 200
        assert [row["id"] for row in response.json()] == [str(doc.id)]


async def test_filename_search_paginates_within_owner_status_and_archive(db_session, async_client):
    stamp = datetime(2026, 11, 1, tzinfo=UTC)
    first = await make_document(
        db_session,
        id=uuid.UUID(int=2),
        original_name="Faktura_100%.pdf",
        created_at=stamp,
    )
    same_time = await make_document(
        db_session,
        user_id=first.user_id,
        id=uuid.UUID(int=1),
        original_name="faktura_100%.jpeg",
        created_at=stamp,
    )
    foreign = await make_document(db_session, original_name="Faktura_100%.pdf")
    archived = await make_document(
        db_session,
        user_id=first.user_id,
        original_name="Faktura_100%.pdf",
        archived_at=stamp,
    )
    for name, status in [("FakturaX100A.pdf", "done"), ("Faktura_100%.pdf", "error")]:
        await make_document(db_session, user_id=first.user_id, original_name=name, status=status)
    authenticate(first.user_id)
    params = {"query": " FAKTURA_100% ", "status": "done", "limit": 1}

    page = await async_client.get("/api/documents", params=params)
    assert page.status_code == 200
    assert [row["id"] for row in page.json()] == [str(first.id)]
    # Updates to the newer part of the list must preserve the next page.
    first.archived_at = stamp
    await make_document(
        db_session,
        user_id=first.user_id,
        original_name="Faktura_100%.png",
        created_at=stamp + timedelta(days=1),
    )
    page = await async_client.get("/api/documents", params={**params, "before": str(first.id)})
    assert page.status_code == 200
    assert [row["id"] for row in page.json()] == [str(same_time.id)]

    foreign_page = await async_client.get(
        "/api/documents", params={**params, "before": str(foreign.id)}
    )
    assert foreign_page.json() == []
    archive_page = await async_client.get(
        "/api/documents", params={**params, "archived": "true", "limit": 5}
    )
    assert {row["id"] for row in archive_page.json()} == {str(first.id), str(archived.id)}


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
