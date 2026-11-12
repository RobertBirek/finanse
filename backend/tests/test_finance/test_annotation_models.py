"""Owner-bound narrative overlays never replace ledger identity."""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.finance.annotation_models import FinanceTag, TransactionAnnotation, TransactionTag
from app.finance.annotation_schemas import AnnotationUpdate, normalize_tag
from app.finance.models import FinancialTransaction
from app.work.models import Project
from tests.test_finance.test_categorization import setup

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_annotations_are_owner_scoped_and_optional(db_session):
    _owner, txn, _, _, _ = await setup(db_session)
    assert await db_session.scalar(select(TransactionAnnotation)) is None
    db_session.add(TransactionAnnotation(transaction_id=txn.id, user_id=uuid.uuid4(), version=1))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_tags_have_one_normalized_identity(db_session):
    owner, _, _, _, _ = await setup(db_session)
    assert normalize_tag("  Wakacje\t2026  ") == ("Wakacje 2026", "wakacje 2026")
    assert normalize_tag("Z\u0307ycie")[1] == "życie"
    db_session.add(FinanceTag(user_id=owner, name="Wakacje", normalized_name="wakacje"))
    await db_session.flush()
    db_session.add(FinanceTag(user_id=owner, name="wakacje", normalized_name="wakacje"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_tag_links_cannot_cross_owners(db_session):
    owner, txn, _, _, _ = await setup(db_session)
    tag = FinanceTag(user_id=uuid.uuid4(), name="Other", normalized_name="other")
    db_session.add(tag)
    await db_session.flush()
    db_session.add(TransactionTag(transaction_id=txn.id, user_id=owner, tag_id=tag.id))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_project_fk_preserves_transaction_on_delete(db_session):
    owner, txn, _, _, _ = await setup(db_session)
    project = Project(user_id=owner, name="Remont")
    db_session.add(project)
    await db_session.flush()
    txn.project_id = project.id
    await db_session.flush()
    db_session.add(
        TransactionAnnotation(transaction_id=txn.id, user_id=owner, note="Keep me", version=1)
    )
    await db_session.commit()
    await db_session.execute(delete(Project).where(Project.id == project.id))
    await db_session.commit()
    await db_session.refresh(txn)
    assert txn.project_id is None
    assert (await db_session.scalar(select(TransactionAnnotation))).note == "Keep me"
    assert await db_session.get(FinancialTransaction, txn.id) is not None


async def test_annotation_schema_rejects_ledger_fields():
    payload = {
        "display_description": None,
        "note": None,
        "tags": [],
        "project_id": None,
        "expected_version": 0,
        "expected_context_snapshot": "a" * 64,
    }
    assert AnnotationUpdate(**payload).tags == []
    for key in ["description", "transaction_date", "postings", "source", "amount_minor"]:
        with pytest.raises(ValidationError):
            AnnotationUpdate(**payload, **{key: "forbidden"})
