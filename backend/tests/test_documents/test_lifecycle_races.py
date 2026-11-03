import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.documents.job_models import DocumentProcessingJob
from app.documents.job_service import create_local_ocr_intent
from app.documents.lifecycle import DocumentLifecycleError, set_document_archived
from app.documents.models import Document
from test_documents.test_lifecycle import make_document

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("winner", ["archive", "admission"])
async def test_archive_and_admission_serialize_on_document_row(db_session, winner):
    doc = await make_document(db_session)
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    locked = asyncio.Event()
    release = asyncio.Event()
    second_started = asyncio.Event()

    async def first():
        async with sessions() as session, session.begin():
            if winner == "archive":
                await set_document_archived(session, doc.user_id, doc.id, archived=True)
            else:
                await create_local_ocr_intent(session, doc.user_id, doc.id, key="winner")
            locked.set()
            await release.wait()

    async def second():
        async with sessions() as session, session.begin():
            # Deliberately keep a stale ORM identity loaded before the winning commit.
            cached = await session.get(Document, doc.id)
            assert cached.archived_at is None
            await locked.wait()
            second_started.set()
            with pytest.raises(
                DocumentLifecycleError,
                match="document_archived" if winner == "archive" else "document_processing_active",
            ):
                if winner == "archive":
                    await create_local_ocr_intent(session, doc.user_id, doc.id, key="loser")
                else:
                    await set_document_archived(session, doc.user_id, doc.id, archived=True)

    task2 = asyncio.create_task(second())
    task1 = asyncio.create_task(first())
    try:
        await asyncio.wait_for(second_started.wait(), 5)
        assert not task2.done()
    finally:
        release.set()
    await asyncio.wait_for(asyncio.gather(task1, task2), 10)
    await db_session.refresh(doc)
    assert (doc.archived_at is not None) == (winner == "archive")
    count = await db_session.scalar(
        select(func.count())
        .select_from(DocumentProcessingJob)
        .where(DocumentProcessingJob.document_id == doc.id)
    )
    assert count == (0 if winner == "archive" else 1)
