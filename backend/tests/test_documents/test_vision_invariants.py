"""Acceptance invariants for the vision-only document path.

The provider boundary is an in-process httpx transport: no image or request can
leave the test process.  Everything else (upload service, durable job, worker
and review service) is real.
"""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_security.test_rate_limit import TRUSTED_ORIGIN

import app.main  # noqa: F401 - registers all models for isolated schema creation
from app.documents import job_service, service, vision_client, vision_worker
from app.documents.job_models import DocumentProcessingJob, DocumentVisionPolicy
from app.documents.models import DocumentExtractionRevision
from app.documents.vision_config import VisionConfig
from app.finance.bills import approve_bill, prepare_bill
from app.finance.bills_schemas import BillApprove, MutationContext
from app.finance.models import Account, Category, FinancialTransaction, Posting
from app.finance.schemas import PostingCreate, TransactionCreate
from app.finance.transactions import create_transaction
from app.identity.models import User
from app.identity.service import create_session
from app.inbox.models import InboxItem
from test_documents.fixtures import valid_jpeg_bytes, valid_pdf_bytes


def _config() -> VisionConfig:
    return VisionConfig(
        "test-provider", "https://vision.example.test/v1", "test-model", "test-key", "p1", "s1"
    )


async def _records(db_session):
    """Serialize complete rows, so a hidden write cannot pass a count assertion."""
    tables = (Account, FinancialTransaction, Posting, InboxItem)
    result: dict[str, list[dict[str, object]]] = {}
    for model in tables:
        rows = (await db_session.execute(select(model))).scalars().all()
        result[model.__tablename__] = [
            {column.name: str(getattr(row, column.name)) for column in model.__table__.columns}
            for row in rows
        ]
    balances = {row.id: 0 for row in (await db_session.execute(select(Account))).scalars()}
    for posting in (await db_session.execute(select(Posting))).scalars():
        if posting.account_id is not None:
            balances[posting.account_id] += (
                posting.base_amount_pln
                if posting.direction == "credit"
                else -posting.base_amount_pln
            )
    result["account_balance_pln"] = [
        {"id": str(key), "balance": value}
        for key, value in sorted(balances.items(), key=lambda item: str(item[0]))
    ]
    return result


def _provider_response(request: httpx.Request) -> httpx.Response:
    assert request.url.host == "vision.example.test"
    payload = {
        "document_type": "receipt",
        "fields": {
            "supplier_name": "Synthetic shop",
            "supplier_tax_id": None,
            "number": None,
            "issue_date": "2026-11-01",
            "sale_date": None,
            "due_date": None,
            "description": "Synthetic receipt",
            "payee_iban": None,
            "total": "12.34",
            "currency": "PLN",
        },
        "warnings": [],
    }
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": json.dumps(payload), "refusal": None},
                }
            ]
        },
    )


@pytest.mark.integration
async def test_new_vision_upload_ready_then_human_review_never_changes_ledger_or_inbox(
    db_session, test_database, tmp_path, monkeypatch
):
    """Removing the no-auto-write boundary would change the full-record snapshot."""
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    config = _config()
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(vision_worker, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(vision_worker, "async_session_factory", sessions)
    monkeypatch.setattr(vision_worker.settings, "DOCUMENT_VISION_ENABLED", True)
    monkeypatch.setattr(vision_worker, "get_vision_config", lambda _: config)
    monkeypatch.setattr(job_service, "get_vision_config", lambda _: config)
    monkeypatch.setattr(
        vision_client,
        "_create_http_client",
        lambda **_: httpx.AsyncClient(transport=httpx.MockTransport(_provider_response)),
    )

    user = User(email="vision-acceptance@example.invalid", password_hash="hash", display_name="QA")
    db_session.add_all(
        (
            user,
            DocumentVisionPolicy(
                id=1,
                enabled=True,
                epoch=7,
                configuration_fingerprint=config.configuration_fingerprint,
            ),
        )
    )
    await db_session.flush()
    legacy_account = Account(user_id=user.id, name="Legacy cash", type="cash", currency="PLN")
    legacy_category = Category(user_id=user.id, name="Legacy category", type="expense")
    db_session.add_all(
        (
            legacy_account,
            legacy_category,
            InboxItem(user_id=user.id, content="Synthetic legacy inbox"),
        )
    )
    await db_session.flush()
    await create_transaction(
        db_session,
        user.id,
        TransactionCreate(
            description="Synthetic legacy payment",
            type="expense",
            postings=[
                PostingCreate(
                    account_id=legacy_account.id,
                    source_amount=500,
                    source_currency="PLN",
                    base_amount_pln=500,
                    fx_rate=1,
                    fx_rate_source="manual",
                    direction="debit",
                ),
                PostingCreate(
                    category_id=legacy_category.id,
                    source_amount=500,
                    source_currency="PLN",
                    base_amount_pln=500,
                    fx_rate=1,
                    fx_rate_source="manual",
                    direction="credit",
                ),
            ],
        ),
    )
    await db_session.flush()
    before = await _records(db_session)
    document, duplicate = await service.store_document(
        db_session, user.id, valid_jpeg_bytes(), "synthetic.jpg", "image/jpeg"
    )
    await db_session.commit()
    assert not duplicate
    job = (await db_session.execute(select(DocumentProcessingJob))).scalar_one()
    revision = await db_session.get(DocumentExtractionRevision, job.revision_id)
    user_id, document_id = user.id, document.id
    assert (document.processing_method, job.kind, job.state, revision.input_method) == (
        "vision",
        "vision",
        "pending",
        "image",
    )
    assert await _records(db_session) == before

    job_id, revision_id = job.id, revision.id
    await vision_worker.process_document_job({}, str(job_id))
    await db_session.rollback()
    job = await db_session.get(DocumentProcessingJob, job_id)
    revision = await db_session.get(DocumentExtractionRevision, revision_id)
    assert (job.state, revision.status, revision.data["fields"]["total"]) == (
        "succeeded",
        "ready",
        "12.34",
    )
    assert await _records(db_session) == before

    # Human approval persists a document record but must not create a ledger entry.
    draft = await prepare_bill(
        db_session, user_id, document_id, context=MutationContext(idempotency_key="human-review")
    )
    await approve_bill(
        db_session,
        user_id,
        draft.id,
        BillApprove(
            version=draft.version,
            kind="receipt",
            supplier_name="Human verified",
            description="Synthetic only",
            total_minor=1234,
            currency="PLN",
        ),
        context=MutationContext(idempotency_key="human-approve"),
    )
    await db_session.commit()
    assert await _records(db_session) == before


@pytest.mark.integration
async def test_legacy_pdf_and_duplicate_never_create_a_vision_call_or_text_llm(
    db_session, tmp_path, monkeypatch
):
    """GET/duplicate/legacy handling must remain inert; only explicit actions make work."""
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(service.settings, "DOCUMENT_VISION_ENABLED", True)
    user = User(email="legacy-acceptance@example.invalid", password_hash="hash", display_name="QA")
    db_session.add_all((user, DocumentVisionPolicy(id=1, enabled=True, epoch=3)))
    await db_session.flush()
    pdf, duplicate = await service.store_document(
        db_session, user.id, valid_pdf_bytes(), "old.pdf", "application/pdf"
    )
    same, duplicate = await service.store_document(
        db_session, user.id, valid_pdf_bytes(), "again.pdf", "application/pdf"
    )
    assert duplicate and same.id == pdf.id and pdf.processing_method == "legacy_ocr"
    assert (await db_session.execute(select(DocumentProcessingJob))).scalars().all() == []
    assert (await db_session.execute(select(DocumentExtractionRevision))).scalars().all() == []


@pytest.mark.integration
async def test_old_image_reads_and_duplicate_are_inert_until_explicit_vision_action(
    async_client, db_session, test_database, tmp_path, monkeypatch
):
    """An old image is never backfilled by reads or a duplicate after policy enable."""
    sessions = async_sessionmaker(test_database, expire_on_commit=False)
    config = _config()
    provider_calls = 0

    def provider(request: httpx.Request) -> httpx.Response:
        nonlocal provider_calls
        provider_calls += 1
        return _provider_response(request)

    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(service.settings, "DOCUMENT_VISION_ENABLED", True)
    monkeypatch.setattr(vision_worker, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(vision_worker, "async_session_factory", sessions)
    monkeypatch.setattr(vision_worker.settings, "DOCUMENT_VISION_ENABLED", True)
    monkeypatch.setattr(vision_worker, "get_vision_config", lambda _: config)
    monkeypatch.setattr(job_service, "get_vision_config", lambda _: config)
    monkeypatch.setattr(
        vision_client,
        "_create_http_client",
        lambda **_: httpx.AsyncClient(transport=httpx.MockTransport(provider)),
    )
    user = User(
        email="old-image-acceptance@example.invalid", password_hash="hash", display_name="QA"
    )
    policy = DocumentVisionPolicy(id=1, enabled=False, epoch=3)
    db_session.add_all((user, policy))
    await db_session.flush()
    old_image, duplicate = await service.store_document(
        db_session, user.id, valid_jpeg_bytes(), "old.jpg", "image/jpeg"
    )
    assert not duplicate and old_image.processing_method == "legacy_ocr"
    await db_session.commit()
    policy.enabled = True
    policy.epoch = 4
    policy.configuration_fingerprint = config.configuration_fingerprint
    session_token, csrf_token, _ = await create_session(db_session, user.id)
    await db_session.commit()
    headers = {
        "Origin": TRUSTED_ORIGIN,
        "X-CSRF-Token": csrf_token,
        "Cookie": f"advisor_session={session_token}; advisor_csrf={csrf_token}",
    }

    reads = [
        await async_client.get("/api/documents", headers=headers),
        await async_client.get(f"/api/documents/{old_image.id}", headers=headers),
        await async_client.get(f"/api/documents/{old_image.id}/review", headers=headers),
        await async_client.get(f"/api/documents/{old_image.id}/original", headers=headers),
        await async_client.get(f"/api/documents/{old_image.id}/preview", headers=headers),
    ]
    assert [response.status_code for response in reads] == [200, 200, 404, 200, 200]
    duplicate_response = await async_client.post(
        "/api/documents/upload",
        headers=headers,
        files={"file": ("again.jpg", valid_jpeg_bytes(), "image/jpeg")},
    )
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["is_duplicate"] is True
    assert (await db_session.execute(select(DocumentProcessingJob))).scalars().all() == []
    assert (await db_session.execute(select(DocumentExtractionRevision))).scalars().all() == []
    assert provider_calls == 0

    explicit = await async_client.post(
        f"/api/documents/{old_image.id}/vision/prepare",
        headers={**headers, "Idempotency-Key": "explicit-old-image"},
    )
    assert explicit.status_code == 202
    job = (await db_session.execute(select(DocumentProcessingJob))).scalar_one()
    revision = await db_session.get(DocumentExtractionRevision, job.revision_id)
    assert (job.kind, revision.input_method, provider_calls) == ("vision", "image", 0)
    await vision_worker.process_document_job({}, str(job.id))
    assert provider_calls == 1


@pytest.mark.integration
async def test_only_explicit_payment_creates_a_balanced_minimum_two_posting_ledger(db_session):
    """A document approval is inert; a separate human payment is the ledger boundary."""
    user = User(email="ledger-acceptance@example.invalid", password_hash="hash", display_name="QA")
    db_session.add(user)
    await db_session.flush()
    debit = Account(user_id=user.id, name="Synthetic cash", type="cash", currency="PLN")
    category = Category(user_id=user.id, name="Synthetic", type="expense")
    db_session.add_all((debit, category))
    await db_session.flush()
    transaction = await create_transaction(
        db_session,
        user.id,
        TransactionCreate(
            description="Explicit synthetic payment",
            type="expense",
            postings=[
                PostingCreate(
                    account_id=debit.id,
                    category_id=None,
                    source_amount=1234,
                    source_currency="PLN",
                    base_amount_pln=1234,
                    fx_rate=1,
                    fx_rate_source="manual",
                    direction="debit",
                ),
                PostingCreate(
                    account_id=None,
                    category_id=category.id,
                    source_amount=1234,
                    source_currency="PLN",
                    base_amount_pln=1234,
                    fx_rate=1,
                    fx_rate_source="manual",
                    direction="credit",
                ),
            ],
        ),
    )
    postings = transaction.postings
    signed = sum(
        item.base_amount_pln if item.direction == "debit" else -item.base_amount_pln
        for item in postings
    )
    assert len(postings) >= 2 and signed == 0
