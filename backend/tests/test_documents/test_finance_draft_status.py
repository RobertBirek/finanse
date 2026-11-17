"""Financial registration is independent of OCR; pure/DB-boundary tests need no DB."""

import datetime as dt
import importlib
import importlib.util
import io
import re
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql


@pytest.fixture
def queries():
    return importlib.import_module("app.documents.finance_draft_queries")


@pytest.mark.asyncio
async def test_finance_summaries_are_batched_and_owner_scoped(queries):
    owner = uuid.uuid4()
    ids = [uuid.uuid4() for _ in range(50)]
    result = SimpleNamespace(
        all=lambda: [
            SimpleNamespace(
                document_id=ids[0],
                state="succeeded",
                error_code=None,
                bill_id=uuid.uuid4(),
                review="approved",
                lifecycle="active",
                revision_id=uuid.uuid4(),
            ),
            SimpleNamespace(
                document_id=ids[1],
                state="pending",
                error_code=None,
                bill_id=None,
                review=None,
                lifecycle=None,
                revision_id=None,
            ),
        ]
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    summary = await queries.get_finance_summaries(db, owner, ids)
    assert summary[ids[0]].review == "approved"
    assert summary[ids[0]].revision_id is not None
    assert summary[ids[1]].state == "pending"
    assert summary[ids[2]].bill_id is None
    assert summary[ids[2]].state == "not_requested"
    assert len(summary) == 50
    db.execute.assert_awaited_once()
    sql = str(db.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "financial_document_sources.user_id" in sql
    assert "financial_documents.user_id" in sql
    assert "document_finance_draft_intents.user_id" in sql
    assert "extracted_text" not in sql
    assert owner in db.execute.call_args.args[0].compile().params.values()


@pytest.mark.asyncio
async def test_empty_finance_summaries_never_query_or_enqueue(queries):
    db = SimpleNamespace(execute=AsyncMock())
    assert await queries.get_finance_summaries(db, uuid.uuid4(), []) == {}
    db.execute.assert_not_awaited()


@pytest.mark.parametrize(
    ("state", "review", "lifecycle"),
    [
        ("not_requested", None, None),
        ("pending", None, None),
        ("needs_review", None, None),
        ("failed", None, None),
        ("succeeded", "draft", "active"),
        ("succeeded", "approved", "active"),
        ("not_requested", "approved", "archived"),
        ("not_requested", "rejected", "cancelled"),
    ],
)
def test_finance_summary_distinguishes_registration_from_recognition(state, review, lifecycle):
    schemas = importlib.import_module("app.documents.finance_draft_schemas")
    value = schemas.FinanceDraftSummary(
        state=state,
        bill_id=uuid.uuid4() if review else None,
        review=review,
        lifecycle=lifecycle,
    )
    assert value.model_dump()["state"] == state
    assert value.review == review
    assert value.lifecycle == lifecycle


def test_models_add_intent_and_nullable_category_without_adopting_legacy():
    from app.documents.models import DocumentExtractionRevision

    models = importlib.import_module("app.documents.finance_draft_models")
    assert models.DocumentFinanceDraftIntent.__table__.c.state.server_default.arg == "pending"
    assert DocumentExtractionRevision.__table__.c.suggested_category_id.nullable
    assert not DocumentExtractionRevision.__table__.c.suggested_category_id.server_default
    intent = models.DocumentFinanceDraftIntent.__table__
    unique = [
        set(c.columns.keys())
        for c in intent.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    ]
    assert {"document_id"} in unique


@pytest.mark.asyncio
async def test_document_response_keeps_link_even_when_latest_recognition_failed(monkeypatch):
    from app.documents import processing_queries, service
    from app.documents.models import Document
    from app.documents.schemas import ReviewSummary

    queries = importlib.import_module("app.documents.finance_draft_queries")
    schemas = importlib.import_module("app.documents.finance_draft_schemas")
    doc_id, owner, bill_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=owner,
        filename="synthetic",
        original_name="synthetic",
        mime_type="application/pdf",
        sha256_hash="a" * 64,
        size_bytes=1,
        storage_path="synthetic",
        status="done",
        archived_at=None,
        attempt_count=1,
        created_at=dt.datetime.now(dt.UTC),
        updated_at=dt.datetime.now(dt.UTC),
        processing_method="legacy_ocr",
    )
    monkeypatch.setattr(
        processing_queries,
        "get_review_summaries",
        AsyncMock(
            return_value={
                doc_id: ReviewSummary(
                    revision_id=uuid.uuid4(),
                    revision=2,
                    status="error",
                    error_code="invalid_model_output",
                )
            }
        ),
    )
    monkeypatch.setattr(processing_queries, "get_local_ocr_summaries", AsyncMock(return_value={}))
    monkeypatch.setattr(
        queries,
        "get_finance_summaries",
        AsyncMock(
            return_value={
                doc_id: schemas.FinanceDraftSummary(
                    bill_id=bill_id, review="approved", lifecycle="active"
                )
            }
        ),
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=list)))
    result = (await service.document_responses(db, owner, [doc]))[0]
    assert result.review.status == "error"
    assert result.finance.bill_id == bill_id
    assert result.finance.review == "approved"


def test_migration_upgrade_is_additive_and_does_not_backfill():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/a6e52f41c9d0_document_finance_draft_intents.py"
    )
    spec = importlib.util.spec_from_file_location("auto_finance_draft_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        module.upgrade()
    sql = output.getvalue()
    assert module.down_revision == "efaf78432563"
    assert "CREATE TABLE document_finance_draft_intents" in sql
    assert "ADD COLUMN suggested_category_id UUID" in sql
    assert "FOREIGN KEY(document_id, user_id)" in sql
    assert not re.search(r"(?im)^\s*(INSERT|UPDATE|DELETE|TRUNCATE|DROP)\s", sql)


@pytest.mark.integration
async def test_real_projection_keeps_owners_and_existing_sources_separate(db_session):
    import app.main  # noqa: F401
    from app.documents.finance_draft_models import DocumentFinanceDraftIntent
    from app.documents.finance_draft_queries import get_finance_summaries
    from app.documents.models import Document
    from app.finance.models import FinancialDocument, FinancialDocumentSource
    from app.identity.models import User

    owner = User(email="draft-status@example.test", password_hash="synthetic", display_name="Owner")
    other = User(email="draft-other@example.test", password_hash="synthetic", display_name="Other")
    db_session.add_all([owner, other])
    await db_session.flush()
    docs = [
        Document(
            user_id=user.id,
            filename="synthetic.pdf",
            original_name="synthetic.pdf",
            mime_type="application/pdf",
            sha256_hash=uuid.uuid4().hex * 2,
            size_bytes=1,
            storage_path="synthetic",
            status="done",
        )
        for user in (owner, owner, other)
    ]
    bill = FinancialDocument(user_id=owner.id, review="draft", lifecycle="active")
    db_session.add_all([*docs, bill])
    await db_session.flush()
    db_session.add_all(
        [
            FinancialDocumentSource(
                user_id=owner.id,
                document_id=docs[0].id,
                financial_document_id=bill.id,
            ),
            DocumentFinanceDraftIntent(user_id=owner.id, document_id=docs[1].id),
        ]
    )
    await db_session.flush()
    result = await get_finance_summaries(db_session, owner.id, [d.id for d in docs])
    assert result[docs[0].id].review == "draft"
    assert result[docs[1].id].state == "pending"
    assert result[docs[2].id].bill_id is None
    assert result[docs[2].id].state == "not_requested"
