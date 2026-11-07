"""Candidates are owned, explainable and read-only; allocation guards still win."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import selectinload

from app.audit.models import AuditEvent
from app.documents.models import Document
from app.finance import bill_payments
from app.finance.bills_schemas import AllocationCreate, MutationContext
from app.finance.models import (
    Account,
    DocumentPaymentAllocation,
    FinanceCommandReceipt,
    FinancialDocument,
    FinancialDocumentSource,
    FinancialTransaction,
    LoanAgreement,
    LoanInstallment,
    LoanPaymentLink,
    Posting,
    TransactionDateMetadata,
)
from app.inbox.models import InboxItem
from tests.test_finance import test_bill_payments as factory
from tests.test_finance.test_account_currency import client_for

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
TODAY = date(2026, 11, 7)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(bill_payments, "_local_today", lambda: TODAY)
    monkeypatch.setattr(factory, "_local_today", lambda: TODAY)
    monkeypatch.setattr(bill_payments.settings, "BILL_PAYMENT_CANDIDATE_DATE_WINDOW_DAYS", 2)


async def payment(db, owner, *, purchase=None, description="Supplier", **kwargs):
    posting_id, account, category = await factory.expense(db, owner, 10000, **kwargs)
    txn = await db.scalar(
        select(FinancialTransaction)
        .join(Posting)
        .where(Posting.id == posting_id)
        .options(selectinload(FinancialTransaction.postings))
    )
    txn.description = description
    if purchase:
        txn.date_metadata = TransactionDateMetadata(
            user_id=owner,
            transaction_id=txn.id,
            purchase_date=purchase,
            purchase_date_source="manual",
            booking_date=txn.date,
            booking_date_source="bank",
        )
    await db.flush()
    return txn, posting_id, account, category


async def page(db, owner, bill, **kwargs):
    return await bill_payments.get_payment_candidates(
        db,
        owner,
        bill.id,
        limit=kwargs.pop("limit", 20),
        offset=kwargs.pop("offset", 0),
        **kwargs,
    )


async def source(db, owner, bill):
    doc = Document(
        user_id=owner,
        filename="fake.pdf",
        original_name="fake.pdf",
        mime_type="application/pdf",
        sha256_hash=uuid.uuid4().hex * 2,
        size_bytes=1,
        storage_path="synthetic/never-read.pdf",
    )
    db.add(doc)
    await db.flush()
    db.add(
        FinancialDocumentSource(user_id=owner, financial_document_id=bill.id, document_id=doc.id)
    )
    await db.flush()
    return doc


async def test_candidate_has_owned_evidence_and_preserves_amounts(db_session):
    db = db_session
    owner = await factory.create_owner(db)
    bill = await factory.setup_bill(db, owner)
    txn, posting, account, category = await payment(db, owner, purchase=date(2026, 10, 30), days=-5)
    bill.sale_date = date(2026, 10, 30)
    another = await factory.setup_bill(db, owner)
    await bill_payments.allocate_payment(
        db,
        owner,
        another.id,
        AllocationCreate(version=another.version, posting_id=posting, amount_minor=4000),
        context=MutationContext(idempotency_key="partial-other-bill"),
    )
    # Category split must not turn one account debit into two candidate amounts.
    credit = next(p for p in txn.postings if p.category_id)
    credit.source_amount = credit.base_amount_pln = 4000
    db.add(
        Posting(
            transaction_id=txn.id,
            category_id=category.id,
            direction="credit",
            source_amount=6000,
            base_amount_pln=6000,
            source_currency="PLN",
            fx_rate=1,
        )
    )
    await db.flush()
    db.expire(txn, ["postings"])
    (row,) = (await page(db, owner, bill)).items
    assert row.amount_minor == 10000
    assert row.unallocated_minor == 6000
    assert row.evidence.currency == "PLN"
    assert row.evidence.purchase_date == date(2026, 10, 30)
    assert row.evidence.booking_date == date(2026, 11, 2)
    assert row.evidence.date_comparison.document_basis == "sale"
    assert row.evidence.date_comparison.delta_days == 0
    bill.payment_account_id = account.id
    assert (await page(db, owner, bill)).items[0].evidence.planned_account_matches is True


async def test_purchase_window_adds_without_narrowing_legacy(db_session):
    db = db_session
    owner = await factory.create_owner(db)
    bill = await factory.setup_bill(db, owner)
    bill.sale_date, bill.due_date = date(2026, 10, 30), date(2026, 11, 30)
    _, posting, _, _ = await payment(db, owner, purchase=date(2026, 10, 30), days=-5)
    assert [r.posting_id for r in (await page(db, owner, bill)).items] == [posting]
    assert "purchase_date_within_window" in (await page(db, owner, bill)).items[0].reasons
    assert (await page(db, owner, bill, date_from=date(2026, 11, 3))).items == []
    assert (await page(db, owner, bill, query="not-the-description")).items == []
    bill.sale_date, bill.due_date = None, date(2026, 10, 1)
    # Old window has no upper bound: Nov2 is not hidden by a new symmetric window.
    assert [r.posting_id for r in (await page(db, owner, bill)).items] == [posting]


@pytest.mark.parametrize("days,visible", [(-3, False), (-2, True), (2, True), (3, False)])
async def test_purchase_window_boundaries_and_old_opt_ins(db_session, days, visible):
    db = db_session
    owner = await factory.create_owner(db)
    bill = await factory.setup_bill(db, owner)
    bill.sale_date, bill.due_date = date(2026, 10, 30), date(2026, 11, 30)
    _, posting, _, _ = await payment(
        db, owner, purchase=bill.sale_date + timedelta(days=days), days=-5
    )
    assert bool((await page(db, owner, bill)).items) is visible
    assert [r.posting_id for r in (await page(db, owner, bill, include_older=True)).items] == [
        posting
    ]
    assert [r.posting_id for r in (await page(db, owner, bill, query="Supplier")).items] == [
        posting
    ]
    assert (await page(db, owner, bill, date_to=date(2026, 11, 1), include_older=True)).items == []


async def test_order_and_pages_use_global_stable_rank(db_session):
    db = db_session
    owner = await factory.create_owner(db)
    bill = await factory.setup_bill(db, owner)
    bill.sale_date = date(2026, 10, 30)
    _, p1, account, _ = await payment(db, owner, purchase=bill.sale_date, description="Unrelated")
    _, p2, _, _ = await payment(db, owner, purchase=date(2026, 10, 29))
    _, p3, _, _ = await payment(db, owner, purchase=bill.sale_date)
    legacy, p4, _, _ = await payment(db, owner, description="Unrelated")
    doc = await source(db, owner, bill)
    db.add(
        InboxItem(
            user_id=owner,
            content="legacy",
            source_type="document",
            target_type="transaction",
            target_id=legacy.id,
            is_processed=True,
            classified_by="legacy",
            agent_suggestion={"document_id": str(doc.id)},
        )
    )
    bill.payment_account_id = account.id
    await db.flush()
    full = await page(db, owner, bill)
    assert [r.posting_id for r in full.items] == [p4, p3, p2, p1]
    assert [
        r.posting_id
        for i in range(4)
        for r in (await page(db, owner, bill, limit=1, offset=i)).items
    ] == [p4, p3, p2, p1]
    assert full.items[1].evidence.planned_account_matches is False
    await bill_payments.allocate_payment(
        db,
        owner,
        bill.id,
        AllocationCreate(version=bill.version, posting_id=p3, amount_minor=1),
        context=MutationContext(idempotency_key="different-planned-account"),
    )


@pytest.mark.parametrize(
    "lifecycle,review,currency,reason",
    [
        ("archived", "draft", "EUR", "document_inactive"),
        ("cancelled", "approved", "PLN", "document_inactive"),
        ("active", "draft", "EUR", "document_unapproved"),
        ("active", "rejected", "PLN", "document_unapproved"),
        ("active", "approved", "EUR", "currency_unsupported"),
        ("active", "approved", "USD", "currency_unsupported"),
    ],
)
async def test_document_unavailable_priority(db_session, lifecycle, review, currency, reason):
    db = db_session
    owner = await factory.create_owner(db)
    bill = await factory.setup_bill(db, owner)
    bill.lifecycle, bill.review, bill.currency = lifecycle, review, currency
    result = await page(db, owner, bill, limit=7, offset=4)
    assert result.items == [] and result.total == 0
    assert (result.limit, result.offset, result.unavailable_reason) == (7, 4, reason)


async def test_fully_reconciled_and_owner_http_boundaries(db_session):
    db = db_session
    owner, other = await factory.create_owner(db), await factory.create_owner(db)
    bill = await factory.setup_bill(db, owner)
    _, posting, _, _ = await payment(db, owner)
    await bill_payments.allocate_payment(
        db,
        owner,
        bill.id,
        AllocationCreate(version=bill.version, posting_id=posting, amount_minor=10000),
        context=MutationContext(idempotency_key="full"),
    )
    result = await page(db, owner, bill)
    assert result.items == []
    assert result.unavailable_reason == "document_reconciled"
    async with client_for(db, owner) as client:
        response = await client.get(f"/api/finance/bills/{bill.id}/candidates")
        assert response.status_code == 200
        assert response.json()["unavailable_reason"] == "document_reconciled"
    async with client_for(db, other) as client:
        assert (await client.get(f"/api/finance/bills/{bill.id}/candidates")).status_code == 404
        assert (
            await client.get(f"/api/finance/bills/{uuid.uuid4()}/candidates")
        ).status_code == 404


@pytest.mark.parametrize(
    "excluded",
    ["pending", "future", "transfer", "income", "fx", "loan", "unbalanced", "owner"],
)
async def test_evidence_never_relaxes_eligibility(db_session, excluded):
    db = db_session
    owner = await factory.create_owner(db)
    bill = await factory.setup_bill(db, owner)
    bill.sale_date = TODAY
    payer = await factory.create_owner(db) if excluded == "owner" else owner
    txn, posting, account, _ = await payment(db, payer, purchase=TODAY)
    if excluded == "pending":
        txn.is_pending = True
    if excluded == "future":
        txn.date = TODAY + timedelta(days=1)
    if excluded in {"transfer", "income"}:
        txn.type = excluded
    if excluded == "fx":
        debit = next(p for p in txn.postings if p.id == posting)
        debit.source_currency = "EUR"
        debit.fx_rate = 4
    if excluded == "unbalanced":
        txn.postings[0].base_amount_pln += 1
    if excluded == "loan":
        loan_account = Account(user_id=owner, name="Loan balance", type="loan", currency="PLN")
        db.add(loan_account)
        await db.flush()
        loan = LoanAgreement(
            user_id=owner,
            name="Synthetic loan",
            account_id=loan_account.id,
            payment_account_id=account.id,
        )
        db.add(loan)
        await db.flush()
        installment = LoanInstallment(
            user_id=owner,
            loan_id=loan.id,
            number=1,
            due_date=TODAY,
            principal_pln=10000,
            interest_pln=0,
            fees_pln=0,
        )
        db.add(installment)
        await db.flush()
        db.add(LoanPaymentLink(user_id=owner, installment_id=installment.id, transaction_id=txn.id))
    await db.flush()
    assert (await page(db, owner, bill, include_older=True)).items == []


async def test_foreign_metadata_and_multiple_sources_are_read_only(db_session):
    db = db_session
    owner, other = await factory.create_owner(db), await factory.create_owner(db)
    bill = await factory.setup_bill(db, owner)
    txn, posting, _, _ = await payment(db, owner, purchase=TODAY)
    txn.date_metadata.user_id = other
    await source(db, owner, bill)
    await source(db, owner, bill)
    await db.flush()

    async def snapshot():
        return [
            list((await db.execute(select(model.__table__).order_by(model.id))).mappings())
            for model in (
                FinancialTransaction,
                Posting,
                TransactionDateMetadata,
                FinancialDocument,
                DocumentPaymentAllocation,
                FinanceCommandReceipt,
                AuditEvent,
            )
        ]

    before = await snapshot()
    result = await page(db, owner, bill)
    assert [r.posting_id for r in result.items] == [posting]
    assert result.items[0].evidence.purchase_date is None
    assert result.items[0].evidence.booking_date_source is None
    assert await snapshot() == before


async def test_date_metadata_reads_are_batched(db_session):
    db = db_session
    owner = await factory.create_owner(db)
    bill = await factory.setup_bill(db, owner)
    await payment(db, owner, purchase=TODAY)
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if "FROM transaction_date_metadata" in statement:
            statements.append(statement)

    engine = db.bind.sync_engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        await page(db, owner, bill)
        first = len(statements)
        for _ in range(9):
            await payment(db, owner, purchase=TODAY)
        statements.clear()
        assert len((await page(db, owner, bill)).items) == 10
        assert len(statements) <= max(first, 1)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
