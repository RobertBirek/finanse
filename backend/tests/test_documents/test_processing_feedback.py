"""Status reads expose real latest work, never enqueue or load extracted content."""

import datetime as dt
import uuid

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents import service
from app.documents.job_models import DocumentProcessingJob as Job
from app.documents.models import Document
from app.documents.models import DocumentExtractionRevision as Revision
from app.identity.models import User

pytestmark = pytest.mark.integration


async def owner(db: AsyncSession, suffix: str = "owner") -> User:
    user = User(email=f"feedback-{suffix}@example.test", password_hash="hash", display_name=suffix)
    db.add(user)
    await db.flush()
    return user


async def document(db: AsyncSession, user: User, **values: object) -> Document:
    doc = Document(
        user_id=user.id,
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
    db.add(doc)
    await db.flush()
    return doc


async def revision(db: AsyncSession, doc: Document, number: int, status: str) -> Revision:
    item = Revision(
        user_id=doc.user_id,
        document_id=doc.id,
        revision=number,
        status=status,
        input_method="image",
        field_provenance={},
        data={"document_type": "other", "fields": {}},
    )
    db.add(item)
    await db.flush()
    return item


async def job(db: AsyncSession, doc: Document, state: str, **values: object) -> Job:
    item = Job(
        user_id=doc.user_id,
        document_id=doc.id,
        kind="local_ocr",
        state=state,
        intent_key=str(uuid.uuid4()),
        request_hash="synthetic",
    )
    for name, value in values.items():
        setattr(item, name, value)
    db.add(item)
    await db.flush()
    return item


async def test_real_latest_local_ocr_summary_is_owner_scoped_and_batched(db_session):
    user, other = await owner(db_session), await owner(db_session, "other")
    docs = [await document(db_session, user) for _ in range(50)]
    await job(db_session, docs[0], "succeeded", created_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC))
    latest = await job(
        db_session, docs[0], "processing", created_at=dt.datetime(2026, 1, 2, tzinfo=dt.UTC)
    )
    await job(
        db_session,
        docs[0],
        "failed",
        user_id=other.id,
        error_code="synthetic-private",
        created_at=dt.datetime(2026, 1, 3, tzinfo=dt.UTC),
    )
    statements = []

    def count_sql(*args):
        statements.append(args[2])

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", count_sql)
    try:
        results = await service.document_responses(db_session, user.id, docs)
    finally:
        event.remove(engine, "before_cursor_execute", count_sql)
    assert results[0].local_ocr_state == "processing"
    assert results[0].local_ocr_job_id == latest.id
    assert results[0].local_ocr_error_code is None
    assert results[1].local_ocr_state is None
    assert len(statements) <= 4
    assert "extracted_text" not in results[0].model_dump()


async def test_review_job_identity_ignores_a_foreign_owner(db_session):
    user, other = await owner(db_session), await owner(db_session, "other")
    doc = await document(db_session, user)
    review = await revision(db_session, doc, 1, "processing")
    work = await job(
        db_session, doc, "processing", kind="vision", revision_id=review.id, user_id=other.id
    )
    result = (await service.document_responses(db_session, user.id, [doc]))[0]
    assert result.review.job_state is None
    assert result.review.job_id is None
    work.user_id = user.id
    await db_session.flush()
    result = (await service.document_responses(db_session, user.id, [doc]))[0]
    assert result.review.job_state == "processing" and result.review.job_id == work.id


async def test_local_ocr_terminal_states_and_errors_do_not_stay_active(db_session):
    user = await owner(db_session)
    doc = await document(db_session, user)
    for index, state in enumerate(
        ("pending", "processing", "succeeded", "failed", "paused", "superseded")
    ):
        code = "local_ocr_failed" if state == "failed" else None
        current = await job(
            db_session,
            doc,
            state,
            error_code=code,
            created_at=dt.datetime(2026, 1, index + 1, tzinfo=dt.UTC),
        )
        response = (await service.document_responses(db_session, user.id, [doc]))[0]
        assert (
            response.local_ocr_state,
            response.local_ocr_job_id,
            response.local_ocr_error_code,
        ) == (state, current.id, code)
        active = await service.get_active_documents(db_session, user.id)
        assert (doc.id in {item.id for item in active}) is (state in {"pending", "processing"})


async def test_active_read_finds_older_work_and_respects_pagination_without_mutation(
    db_session, async_client
):
    from app.documents.router import get_current_user
    from app.main import app

    user, other = await owner(db_session), await owner(db_session, "other")
    old = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    legacy = await document(
        db_session, user, processing_method="legacy_ocr", status="pending", created_at=old
    )
    vision = await document(db_session, user, created_at=old)
    rev = await revision(db_session, vision, 1, "ready")
    await job(db_session, vision, "processing", kind="vision", revision_id=rev.id)
    local = await document(db_session, user, created_at=old)
    await revision(db_session, local, 1, "ready")
    await job(db_session, local, "processing")
    text = await document(db_session, user, processing_method="legacy_ocr", created_at=old)
    text_rev = await revision(db_session, text, 1, "pending")
    text_rev.input_method = "text"
    stale = await document(db_session, user)
    await revision(db_session, stale, 1, "pending")
    await revision(db_session, stale, 2, "ready")
    paused = await document(db_session, user)
    paused_rev = await revision(db_session, paused, 1, "pending")
    await job(db_session, paused, "paused", kind="vision", revision_id=paused_rev.id)
    await job(db_session, paused, "processing", created_at=old)
    await job(db_session, paused, "paused")
    for _ in range(60):
        await document(db_session, user)
    await document(db_session, other, processing_method="legacy_ocr", status="processing")
    await db_session.flush()
    before = await db_session.scalar(select(func.count()).select_from(Job))
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        first = await async_client.get("/api/documents/active", params={"limit": 2})
        second = await async_client.get("/api/documents/active", params={"limit": 2, "offset": 2})
        assert first.status_code == second.status_code == 200
        assert {row["id"] for row in first.json() + second.json()} == {
            str(x.id) for x in (legacy, vision, local, text)
        }
        assert len(first.json()) == len(second.json()) == 2
        app.dependency_overrides[get_current_user] = lambda: other
        foreign = await async_client.get("/api/documents/active")
        assert len(foreign.json()) == 1
        assert all(row["user_id"] == str(other.id) for row in foreign.json())
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert await db_session.scalar(select(func.count()).select_from(Job)) == before
