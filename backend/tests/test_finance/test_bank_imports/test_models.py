import hashlib
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document
from app.finance.imports.models import ImportSource
from app.finance.imports.service import create_batch
from app.identity.models import User

pytestmark = pytest.mark.integration


async def source_document(db: AsyncSession, owner: User) -> Document:
    document = Document(
        user_id=owner.id,
        filename=uuid.uuid4().hex + ".csv",
        original_name="synthetic.csv",
        mime_type="text/csv",
        sha256_hash=hashlib.sha256(b"synthetic").hexdigest(),
        size_bytes=9,
        storage_path="/only-test-fixture/synthetic.csv",
        processing_method="bank_import",
        status="done",
    )
    db.add(document)
    await db.flush()
    return document


async def test_source_cannot_attach_another_owners_document(
    db_session: AsyncSession,
    owner: User,
    other_owner: User,
) -> None:
    document = await source_document(db_session, owner)
    batch = await create_batch(db_session, other_owner.id, "statement")
    with pytest.raises(IntegrityError):
        await rejected_source_insert(db_session, other_owner.id, batch.id, document.id)


async def rejected_source_insert(
    db_session: AsyncSession,
    owner_id: uuid.UUID,
    batch_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:
    async with db_session.begin_nested():
        db_session.add(
            ImportSource(
                user_id=owner_id,
                batch_id=batch_id,
                document_id=document_id,
                kind="statement",
            )
        )
        await db_session.flush()


async def test_same_document_and_kind_cannot_start_two_imports(
    db_session: AsyncSession,
    owner: User,
) -> None:
    document = await source_document(db_session, owner)
    first = await create_batch(db_session, owner.id, "statement")
    second = await create_batch(db_session, owner.id, "statement")
    db_session.add(
        ImportSource(user_id=owner.id, batch_id=first.id, document_id=document.id, kind="statement")
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await rejected_source_insert(db_session, owner.id, second.id, document.id)


async def test_batch_kind_and_source_kind_cannot_disagree(
    db_session: AsyncSession, owner: User
) -> None:
    document = await source_document(db_session, owner)
    batch = await create_batch(db_session, owner.id, "loan_schedule")
    with pytest.raises(IntegrityError):
        await rejected_source_insert(db_session, owner.id, batch.id, document.id)
