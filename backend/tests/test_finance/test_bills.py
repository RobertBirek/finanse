import uuid

import pytest
from sqlalchemy import func, select

from app.documents.models import Document, DocumentExtractionRevision
from app.finance.bills import (
    approve_bill,
    find_duplicate_bills,
    prepare_bill,
    set_bill_lifecycle,
)
from app.finance.bills_schemas import BillApprove, MutationContext
from app.finance.models import Posting
from app.identity.models import User
from app.inbox.models import InboxItem

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def source(db, owner: uuid.UUID) -> Document:
    document = Document(
        user_id=owner,
        filename="invoice.pdf",
        original_name="invoice.pdf",
        mime_type="application/pdf",
        sha256_hash=uuid.uuid4().hex * 2,
        size_bytes=1,
        storage_path="test/invoice.pdf",
    )
    db.add(document)
    await db.flush()
    return document


async def owner(db) -> uuid.UUID:
    user = User(email=f"{uuid.uuid4()}@example.test", password_hash="x", display_name="Owner")
    db.add(user)
    await db.flush()
    return user.id


async def test_approve_invoice_has_zero_posting_delta(db_session) -> None:
    user_id = await owner(db_session)
    document = await source(db_session, user_id)
    draft = await prepare_bill(
        db_session, user_id, document.id, context=MutationContext(idempotency_key="prepare")
    )
    before = await db_session.scalar(select(func.count()).select_from(Posting))

    approved = await approve_bill(
        db_session,
        user_id,
        draft.id,
        BillApprove(
            version=draft.version,
            kind="invoice",
            supplier_name="Supplier",
            description="Invoice",
            total_minor=10_000,
            currency="PLN",
            declaration="payable",
        ),
        context=MutationContext(idempotency_key="approve"),
    )

    after = await db_session.scalar(select(func.count()).select_from(Posting))
    assert (approved.paid_minor, approved.remaining_minor) == (0, 10_000)
    assert after == before == 0


async def test_receipt_declared_paid_not_reconciled(db_session) -> None:
    user_id = await owner(db_session)
    document = await source(db_session, user_id)
    draft = await prepare_bill(
        db_session, user_id, document.id, context=MutationContext(idempotency_key="prepare")
    )
    approved = await approve_bill(
        db_session,
        user_id,
        draft.id,
        BillApprove(
            version=draft.version,
            kind="receipt",
            supplier_name="Shop",
            description="Receipt",
            total_minor=100,
            currency="PLN",
        ),
        context=MutationContext(idempotency_key="approve"),
    )
    assert approved.declaration == "declared_paid"
    assert (approved.paid_minor, approved.remaining_minor, approved.reconciliation) == (
        0,
        100,
        "none",
    )


async def test_idempotency_replays_original_snapshot(db_session) -> None:
    user_id = await owner(db_session)
    document = await source(db_session, user_id)
    draft = await prepare_bill(
        db_session, user_id, document.id, context=MutationContext(idempotency_key="prepare")
    )
    archived = await set_bill_lifecycle(
        db_session,
        user_id,
        draft.id,
        "archived",
        draft.version,
        context=MutationContext(idempotency_key="archive"),
    )
    reopened = await set_bill_lifecycle(
        db_session,
        user_id,
        draft.id,
        "active",
        archived.version,
        context=MutationContext(idempotency_key="reopen"),
    )
    replay = await set_bill_lifecycle(
        db_session,
        user_id,
        draft.id,
        "archived",
        draft.version,
        context=MutationContext(idempotency_key="archive"),
    )
    assert (replay.lifecycle, replay.version) == ("archived", archived.version)
    assert reopened.lifecycle == "active"


async def test_duplicate_fallback_warns_when_number_has_no_normalized_nip(db_session) -> None:
    user_id = await owner(db_session)
    first_document = await source(db_session, user_id)
    first = await prepare_bill(
        db_session,
        user_id,
        first_document.id,
        context=MutationContext(idempotency_key="first-prepare"),
    )
    await approve_bill(
        db_session,
        user_id,
        first.id,
        BillApprove(
            version=first.version,
            kind="invoice",
            supplier_name="Supplier",
            number="FV/1",
            issue_date=__import__("datetime").date(2026, 10, 1),
            description="First",
            total_minor=100,
            currency="PLN",
        ),
        context=MutationContext(idempotency_key="first-approve"),
    )
    candidates = await find_duplicate_bills(
        db_session,
        user_id,
        BillApprove(
            version=1,
            kind="invoice",
            supplier_name="Supplier",
            number="FV/2",
            issue_date=__import__("datetime").date(2026, 10, 1),
            description="Second",
            total_minor=100,
            currency="PLN",
        ),
    )
    assert [(candidate.id, candidate.reasons) for candidate in candidates] == [
        (first.id, ["supplier_amount_currency"])
    ]


@pytest.mark.parametrize("document_type", ["unsupported", "statement", "loan_schedule", "multiple"])
async def test_non_bill_review_types_prepare_empty_draft(db_session, document_type: str) -> None:
    user_id = await owner(db_session)
    document = await source(db_session, user_id)
    db_session.add(
        DocumentExtractionRevision(
            user_id=user_id,
            document_id=document.id,
            revision=1,
            status="ready",
            data={
                "document_type": document_type,
                "fields": {"supplier_name": "Never copied", "total": "10.00", "currency": "PLN"},
                "provenance": {},
                "parser_version": "test",
            },
            field_provenance={},
        )
    )
    await db_session.flush()
    draft = await prepare_bill(
        db_session,
        user_id,
        document.id,
        context=MutationContext(idempotency_key=f"prepare-{document_type}"),
    )
    assert (
        draft.kind,
        draft.supplier_name,
        draft.total_minor,
        draft.currency,
        draft.paid_minor,
    ) == (None, None, None, None, 0)


async def test_processed_legacy_target_preserved(db_session) -> None:
    user_id = await owner(db_session)
    document = await source(db_session, user_id)
    target_id = uuid.uuid4()
    suggestion = {"document_id": str(document.id), "status": "processed"}
    inbox = InboxItem(
        user_id=user_id,
        content="legacy",
        source_type="document",
        target_type="transaction",
        target_id=target_id,
        is_processed=True,
        classified_by="legacy",
        agent_suggestion=suggestion,
    )
    db_session.add(inbox)
    await db_session.flush()
    draft = await prepare_bill(
        db_session, user_id, document.id, context=MutationContext(idempotency_key="legacy-prepare")
    )
    await approve_bill(
        db_session,
        user_id,
        draft.id,
        BillApprove(
            version=draft.version,
            kind="invoice",
            supplier_name="Legacy supplier",
            description="Legacy invoice",
            total_minor=100,
            currency="PLN",
        ),
        context=MutationContext(idempotency_key="legacy-approve"),
    )
    await db_session.refresh(inbox)
    assert (inbox.is_processed, inbox.target_type, inbox.target_id, inbox.agent_suggestion) == (
        True,
        "transaction",
        target_id,
        suggestion,
    )
