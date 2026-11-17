"""Domain-boundary tests: recognition is never a payment or a second bill."""

import importlib
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def drafts():
    return importlib.import_module("app.documents.finance_drafts")


def scalar(value):
    return SimpleNamespace(scalar_one_or_none=lambda: value, scalar_one=lambda: value)


def ready_revision(owner, doc_id, **fields):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=owner,
        document_id=doc_id,
        status="ready",
        warnings=[],
        data={
            "document_type": "invoice",
            "fields": {
                "supplier_name": "Synthetic",
                "description": "Subscription",
                "total": "75.00",
                "currency": "PLN",
                **fields,
            },
            "provenance": {},
            "parser_version": None,
        },
    )


def setup_draft(drafts, *, status="pending"):
    owner, doc_id = uuid.uuid4(), uuid.uuid4()
    doc = SimpleNamespace(id=doc_id, user_id=owner, archived_at=None, status="done")
    intent = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=owner,
        document_id=doc_id,
        state=status,
        revision_id=None,
        bill_id=None,
        error_code=None,
    )
    revision = ready_revision(owner, doc_id)
    db = SimpleNamespace(
        get=AsyncMock(return_value=intent),
        execute=AsyncMock(
            side_effect=[scalar(doc), scalar(intent), scalar(None), scalar(revision)]
        ),
        flush=AsyncMock(),
    )

    @asynccontextmanager
    async def savepoint():
        yield

    db.begin_nested = savepoint
    return db, doc, intent, revision


@pytest.mark.asyncio
async def test_supported_recognition_creates_one_unapproved_draft(drafts, monkeypatch):
    db, doc, intent, revision = setup_draft(drafts)
    bill = SimpleNamespace(id=uuid.uuid4(), review="draft", declaration="unknown")
    prepare = AsyncMock(return_value=bill)
    monkeypatch.setattr(drafts, "prepare_bill", prepare)
    result = await drafts.prepare_pending_finance_draft(db, intent.id)
    assert result == "succeeded"
    assert intent.state == "succeeded"
    assert intent.bill_id == bill.id
    assert intent.revision_id == revision.id
    assert prepare.call_args.args[1:3] == (doc.user_id, doc.id)
    assert prepare.call_args.kwargs["context"].performed_by == "system"
    assert bill.review == "draft"
    assert bill.declaration == "unknown"


@pytest.mark.asyncio
async def test_delivery_replay_never_prepares_or_overwrites_a_bill(drafts, monkeypatch):
    db, _, intent, _ = setup_draft(drafts, status="succeeded")
    prepare = AsyncMock()
    monkeypatch.setattr(drafts, "prepare_bill", prepare)
    db.execute.side_effect = [
        scalar(SimpleNamespace(id=intent.document_id, user_id=intent.user_id, archived_at=None)),
        scalar(intent),
    ]
    assert await drafts.prepare_pending_finance_draft(db, intent.id) == "succeeded"
    prepare.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_source_is_preserved_without_preparing_again(drafts, monkeypatch):
    db, doc, intent, _ = setup_draft(drafts)
    source = SimpleNamespace(financial_document_id=uuid.uuid4())
    db.execute.side_effect = [scalar(doc), scalar(intent), scalar(source)]
    prepare = AsyncMock()
    monkeypatch.setattr(drafts, "prepare_bill", prepare)
    assert await drafts.prepare_pending_finance_draft(db, intent.id) == "succeeded"
    assert intent.bill_id == source.financial_document_id
    prepare.assert_not_awaited()


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"supplier_name": None}, "missing_required_fields"),
        ({"description": None}, "missing_required_fields"),
        ({"total": None}, "missing_required_fields"),
        ({"total": "0"}, "invalid_review"),
        ({"currency": None}, "missing_required_fields"),
    ],
)
@pytest.mark.asyncio
async def test_incomplete_review_is_not_silently_approved(drafts, monkeypatch, change, code):
    db, doc, intent, _ = setup_draft(drafts)
    revision = ready_revision(doc.user_id, doc.id, **change)
    db.execute.side_effect = [scalar(doc), scalar(intent), scalar(None), scalar(revision)]
    prepare = AsyncMock()
    monkeypatch.setattr(drafts, "prepare_bill", prepare)
    assert await drafts.prepare_pending_finance_draft(db, intent.id) == "needs_review"
    assert intent.error_code == code
    prepare.assert_not_awaited()


@pytest.mark.asyncio
async def test_statement_and_archive_never_become_an_invoice(drafts, monkeypatch):
    for archive in (False, True):
        db, doc, intent, revision = setup_draft(drafts)
        doc.archived_at = object() if archive else None
        revision.data["document_type"] = "statement"
        db.execute.side_effect = [scalar(doc), scalar(intent), scalar(None), scalar(revision)]
        prepare = AsyncMock()
        monkeypatch.setattr(drafts, "prepare_bill", prepare)
        assert await drafts.prepare_pending_finance_draft(db, intent.id) == "needs_review"
        prepare.assert_not_awaited()


@pytest.mark.asyncio
async def test_registration_error_does_not_repeat_ocr_or_provider(drafts, monkeypatch):
    db, _, intent, _ = setup_draft(drafts)
    monkeypatch.setattr(drafts, "prepare_bill", AsyncMock(side_effect=ValueError("private")))
    assert await drafts.prepare_pending_finance_draft(db, intent.id) == "failed"
    assert intent.error_code == "draft_registration_failed"
    assert "private" not in intent.error_code


@pytest.mark.asyncio
async def test_create_intent_is_owner_checked_and_replays_existing(drafts):
    from app.documents.finance_draft_models import DocumentFinanceDraftIntent
    from app.documents.models import Document

    owner, doc_id = uuid.uuid4(), uuid.uuid4()
    doc = Document(id=doc_id, user_id=owner, archived_at=None)
    intent = DocumentFinanceDraftIntent(id=uuid.uuid4(), user_id=owner, document_id=doc_id)
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[scalar(doc), scalar(intent)]),
        add=lambda _: pytest.fail("duplicate intent"),
        flush=AsyncMock(),
    )
    assert await drafts.create_finance_draft_intent(db, owner, doc_id) is intent
    db.execute.side_effect = [scalar(None)]
    with pytest.raises(LookupError):
        await drafts.create_finance_draft_intent(db, uuid.uuid4(), doc_id)


@pytest.mark.parametrize("duplicate", [False, True])
@pytest.mark.asyncio
async def test_auto_draft_upload_hook_is_new_upload_only(monkeypatch, duplicate):
    from app.documents import service
    from app.documents.models import Document

    drafts = importlib.import_module("app.documents.finance_drafts")
    owner = uuid.uuid4()
    existing = Document(id=uuid.uuid4(), user_id=owner, status="done") if duplicate else None
    added = []

    async def flush():
        for row in added:
            if row.id is None:
                row.id = uuid.uuid4()

    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[None, None, scalar(existing)]),
        add=added.append,
        flush=flush,
    )
    monkeypatch.setattr(
        service, "validate_document_content", AsyncMock(return_value="application/pdf")
    )
    monkeypatch.setattr(service, "enforce_storage_admission", AsyncMock())
    monkeypatch.setattr(service, "_write_document_content", lambda *args: None)
    create = AsyncMock()
    monkeypatch.setattr(drafts, "create_finance_draft_intent", create)
    result, is_duplicate = await service.store_document(
        db, owner, b"synthetic", "a.pdf", "application/pdf"
    )
    assert is_duplicate is duplicate
    assert result.user_id == owner
    if duplicate:
        assert result is existing
        create.assert_not_awaited()
    else:
        assert result.status == "pending"
        create.assert_awaited_once_with(db, owner, result.id)
