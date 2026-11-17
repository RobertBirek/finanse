"""Only CI's newly owned PostgreSQL may execute these transaction/concurrency cases."""

import uuid

import pytest
from sqlalchemy import func, select

import app.main  # noqa: F401
from app.documents.finance_draft_models import DocumentFinanceDraftIntent as Intent
from app.documents.finance_drafts import create_finance_draft_intent, prepare_pending_finance_draft
from app.documents.models import Document, DocumentExtractionRevision
from app.finance.models import FinancialDocument, FinancialDocumentSource, FinancialTransaction
from app.identity.models import User

pytestmark = pytest.mark.integration


async def setup(db, *, complete=True):
    owner = User(
        email=f"draft-{uuid.uuid4()}@example.test", password_hash="synthetic", display_name="Owner"
    )
    db.add(owner)
    await db.flush()
    document = Document(
        user_id=owner.id,
        filename="synthetic.pdf",
        original_name="synthetic.pdf",
        mime_type="application/pdf",
        sha256_hash=uuid.uuid4().hex * 2,
        size_bytes=1,
        storage_path="synthetic",
        status="done",
    )
    db.add(document)
    await db.flush()
    revision = DocumentExtractionRevision(
        user_id=owner.id,
        document_id=document.id,
        revision=1,
        status="ready",
        data={
            "document_type": "invoice",
            "fields": {
                "supplier_name": "Synthetic",
                "description": "Subscription",
                "total": "75.00" if complete else None,
                "currency": "PLN",
            },
            "provenance": {},
            "parser_version": None,
        },
        field_provenance={},
        warnings=[],
    )
    db.add(revision)
    await db.flush()
    return owner, document, revision


async def test_real_replay_creates_one_draft_without_monetary_side_effects(db_session):
    owner, document, revision = await setup(db_session)
    before = await db_session.scalar(select(func.count()).select_from(FinancialTransaction))
    intent = await create_finance_draft_intent(db_session, owner.id, document.id)
    assert await create_finance_draft_intent(db_session, owner.id, document.id) is intent
    assert await prepare_pending_finance_draft(db_session, intent.id) == "succeeded"
    await db_session.flush()
    assert await prepare_pending_finance_draft(db_session, intent.id) == "succeeded"
    bill = await db_session.get(FinancialDocument, intent.bill_id)
    assert (bill.review, bill.declaration, bill.total_minor, bill.currency) == (
        "draft",
        "unknown",
        None,
        None,
    )
    assert intent.revision_id == revision.id
    assert await db_session.scalar(select(func.count()).select_from(Intent)) == 1
    assert await db_session.scalar(select(func.count()).select_from(FinancialDocumentSource)) == 1
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == before


async def test_missing_fields_stop_and_new_review_can_resume_without_new_intent(db_session):
    owner, document, revision = await setup(db_session, complete=False)
    intent = await create_finance_draft_intent(db_session, owner.id, document.id)
    assert await prepare_pending_finance_draft(db_session, intent.id) == "needs_review"
    assert intent.bill_id is None
    new_revision = DocumentExtractionRevision(
        user_id=owner.id,
        document_id=document.id,
        revision=2,
        status="ready",
        data={**revision.data, "fields": {**revision.data["fields"], "total": "75.00"}},
        field_provenance={},
        warnings=[],
    )
    db_session.add(new_revision)
    await db_session.flush()
    assert await prepare_pending_finance_draft(db_session, intent.id) == "succeeded"
    assert intent.revision_id == new_revision.id


async def test_two_deliveries_skip_locked_document_then_replay_one_bill(test_database):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    async with sessions() as seed:
        owner, document, _ = await setup(seed)
        intent = await create_finance_draft_intent(seed, owner.id, document.id)
        await seed.commit()
    async with sessions() as first, sessions() as second:
        assert await prepare_pending_finance_draft(first, intent.id) == "succeeded"
        assert await prepare_pending_finance_draft(second, intent.id) == "not_claimed"
        await second.rollback()
        await first.commit()
        assert await prepare_pending_finance_draft(second, intent.id) == "succeeded"
        assert await second.scalar(select(func.count()).select_from(FinancialDocumentSource)) == 1
