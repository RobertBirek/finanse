import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import worker
from app.documents import review_service
from app.documents.lifecycle import DocumentLifecycleError, set_document_archived
from app.documents.models import DocumentText
from app.documents.review_schemas import ReviewSuggestion
from test_documents.test_lifecycle import make_document, make_revision

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["legacy", "text"])
async def test_archive_rejects_while_running_worker_holds_document_lock(
    db_session, monkeypatch, kind
):
    doc = await make_document(
        db_session, processing_method="legacy_ocr", status="pending" if kind == "legacy" else "done"
    )
    revision = None
    if kind == "text":
        revision = await make_revision(db_session, doc, status="pending", method="text")
        db_session.add(DocumentText(document_id=doc.id, extracted_text="synthetic"))
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_ocr(_db, _doc):
        started.set()
        await release.wait()

    async def fake_extract(_text):
        started.set()
        await release.wait()
        return ReviewSuggestion.model_validate(
            {"document_type": "other", "fields": {}, "provenance": {}}
        )

    monkeypatch.setattr(worker, "async_session_factory", sessions)
    monkeypatch.setattr(worker, "_process_content", fake_ocr)
    monkeypatch.setattr(review_service, "extract_review_data", fake_extract)

    async def process():
        if kind == "legacy":
            await worker.process_document({}, str(doc.id))
        else:
            async with sessions() as session, session.begin():
                await review_service.process_review_revision(session, revision.id)

    async def archive():
        async with sessions() as session, session.begin():
            with pytest.raises(DocumentLifecycleError, match="document_processing_active"):
                await set_document_archived(session, doc.user_id, doc.id, archived=True)

    task = asyncio.create_task(process())
    try:
        await asyncio.wait_for(started.wait(), 5)
        await asyncio.wait_for(archive(), 1)
        assert not release.is_set()
    finally:
        release.set()
        await asyncio.wait_for(task, 10)
    await db_session.refresh(doc)
    assert doc.archived_at is None
