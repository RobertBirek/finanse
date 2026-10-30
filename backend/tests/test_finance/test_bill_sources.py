import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit.models import AuditEvent
from app.documents.models import Document
from app.documents.service import delete_document
from app.finance.bills import attach_source, prepare_bill
from app.finance.bills_schemas import MutationContext
from app.finance.models import FinancialDocumentSource
from app.identity.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def make_document(db, owner: uuid.UUID, name: str) -> Document:
    doc = Document(
        user_id=owner,
        filename=name,
        original_name=name,
        mime_type="application/pdf",
        sha256_hash=uuid.uuid4().hex * 2,
        size_bytes=1,
        storage_path=f"test/{name}",
    )
    db.add(doc)
    await db.flush()
    return doc


async def owner(db) -> uuid.UUID:
    user = User(email=f"{uuid.uuid4()}@example.test", password_hash="x", display_name="Owner")
    db.add(user)
    await db.flush()
    return user.id


async def test_photo_pdf_attach_one_purchase(db_session) -> None:
    user_id = await owner(db_session)
    photo = await make_document(db_session, user_id, "photo.jpg")
    pdf = await make_document(db_session, user_id, "invoice.pdf")
    bill = await prepare_bill(
        db_session, user_id, photo.id, context=MutationContext(idempotency_key="prepare")
    )
    attached = await attach_source(
        db_session,
        user_id,
        bill.id,
        pdf.id,
        bill.version,
        context=MutationContext(idempotency_key="attach"),
    )
    assert {item.document_id for item in attached.sources} == {photo.id, pdf.id}


async def test_two_sessions_prepare_same_source_one_bill(db_session) -> None:
    user_id = await owner(db_session)
    document = await make_document(db_session, user_id, "one.pdf")
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    first_ready = asyncio.Event()
    release_first = asyncio.Event()

    async def first_command():
        async with sessions() as session, session.begin():
            result = await prepare_bill(
                session, user_id, document.id, context=MutationContext(idempotency_key="one")
            )
            first_ready.set()
            await release_first.wait()
            return result

    async def second_command():
        await first_ready.wait()
        async with sessions() as session, session.begin():
            return await prepare_bill(
                session, user_id, document.id, context=MutationContext(idempotency_key="two")
            )

    first_task = asyncio.create_task(first_command())
    second_task = asyncio.create_task(second_command())
    await first_ready.wait()
    await asyncio.sleep(0)
    assert not second_task.done()
    release_first.set()
    first, second = await asyncio.gather(first_task, second_task)
    sources = list(
        (
            await db_session.execute(
                select(FinancialDocumentSource).where(
                    FinancialDocumentSource.document_id == document.id
                )
            )
        ).scalars()
    )
    assert first.id == second.id
    assert len(sources) == 1


async def test_linked_original_delete_rejected(db_session) -> None:
    user_id = await owner(db_session)
    document = await make_document(db_session, user_id, "retained.pdf")
    await prepare_bill(
        db_session, user_id, document.id, context=MutationContext(idempotency_key="prepare")
    )
    with pytest.raises(ValueError, match="linked"):
        await delete_document(db_session, user_id, document.id)


async def test_source_move_audits_both_bill_records(db_session) -> None:
    user_id = await owner(db_session)
    original = await make_document(db_session, user_id, "original.pdf")
    destination_source = await make_document(db_session, user_id, "destination.pdf")
    old = await prepare_bill(
        db_session, user_id, original.id, context=MutationContext(idempotency_key="old")
    )
    destination = await prepare_bill(
        db_session,
        user_id,
        destination_source.id,
        context=MutationContext(idempotency_key="destination"),
    )
    await attach_source(
        db_session,
        user_id,
        destination.id,
        original.id,
        destination.version,
        context=MutationContext(idempotency_key="move"),
    )
    events = list(
        (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_id.in_([str(old.id), str(destination.id)]),
                    AuditEvent.action.in_(["detach_source", "attach_source"]),
                )
            )
        ).scalars()
    )
    assert {(event.entity_id, event.action) for event in events} == {
        (str(old.id), "detach_source"),
        (str(destination.id), "attach_source"),
    }
    assert all(event.new_state["document_id"] == str(original.id) for event in events)
