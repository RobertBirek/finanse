import uuid

import pytest
from sqlalchemy import select

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
    first = await prepare_bill(
        db_session, user_id, document.id, context=MutationContext(idempotency_key="one")
    )
    second = await prepare_bill(
        db_session, user_id, document.id, context=MutationContext(idempotency_key="two")
    )
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
