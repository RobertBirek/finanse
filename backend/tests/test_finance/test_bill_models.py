from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.documents.models import Document
from app.finance.bills_schemas import BillApprove
from app.finance.models import (
    Account,
    Category,
    DocumentPaymentAllocation,
    FinancialDocument,
    FinancialDocumentSource,
    FinancialTransaction,
    Posting,
    RecurringOccurrenceCoverage,
    ScheduledFinanceItem,
)


@pytest.mark.integration
async def test_source_unique_even_after_archive(db_session):
    user_id = __import__("uuid").uuid4()
    document = Document(
        user_id=user_id,
        filename="source.pdf",
        original_name="source.pdf",
        mime_type="application/pdf",
        sha256_hash="0" * 64,
        size_bytes=1,
        storage_path="private/source.pdf",
    )
    first_bill = FinancialDocument(user_id=user_id, lifecycle="archived")
    second_bill = FinancialDocument(user_id=user_id)
    db_session.add_all([document, first_bill, second_bill])
    await db_session.flush()
    db_session.add_all(
        [
            FinancialDocumentSource(
                user_id=user_id, financial_document_id=first_bill.id, document_id=document.id
            ),
            FinancialDocumentSource(
                user_id=user_id, financial_document_id=second_bill.id, document_id=document.id
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.integration
async def test_allocation_positive_and_unique(db_session):
    user_id = __import__("uuid").uuid4()
    bill = FinancialDocument(user_id=user_id)
    transaction = FinancialTransaction(user_id=user_id, description="Test", type="expense")
    db_session.add_all([bill, transaction])
    await db_session.flush()
    posting = Posting(
        transaction_id=transaction.id,
        source_amount=1,
        source_currency="PLN",
        base_amount_pln=1,
        direction="debit",
    )
    db_session.add(posting)
    await db_session.flush()
    db_session.add(
        DocumentPaymentAllocation(
            user_id=user_id,
            financial_document_id=bill.id,
            posting_id=posting.id,
            amount_minor=0,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()
    bill = FinancialDocument(user_id=user_id)
    transaction = FinancialTransaction(user_id=user_id, description="Duplicate", type="expense")
    db_session.add_all([bill, transaction])
    await db_session.flush()
    posting = Posting(
        transaction_id=transaction.id,
        source_amount=1,
        source_currency="PLN",
        base_amount_pln=1,
        direction="debit",
    )
    db_session.add(posting)
    await db_session.flush()
    db_session.add(
        DocumentPaymentAllocation(
            user_id=user_id,
            financial_document_id=bill.id,
            posting_id=posting.id,
            amount_minor=1,
        )
    )
    await db_session.flush()
    db_session.add(
        DocumentPaymentAllocation(
            user_id=user_id,
            financial_document_id=bill.id,
            posting_id=posting.id,
            amount_minor=1,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.integration
async def test_coverage_occurrence_unique(db_session):
    user_id = __import__("uuid").uuid4()
    account = Account(user_id=user_id, name="Account", type="checking")
    category = Category(user_id=user_id, name="Category", type="expense")
    db_session.add_all([account, category])
    await db_session.flush()
    item = ScheduledFinanceItem(
        user_id=user_id,
        name="Recurring",
        type="expense",
        account_id=account.id,
        category_id=category.id,
        currency="PLN",
        due_day=1,
        amount_method="fixed",
        fixed_amount_pln=1,
    )
    first_bill = FinancialDocument(user_id=user_id)
    second_bill = FinancialDocument(user_id=user_id)
    db_session.add_all([item, first_bill, second_bill])
    await db_session.flush()
    db_session.add_all(
        [
            RecurringOccurrenceCoverage(
                user_id=user_id,
                scheduled_item_id=item.id,
                occurrence_date=date(2026, 10, 28),
                financial_document_id=first_bill.id,
            ),
            RecurringOccurrenceCoverage(
                user_id=user_id,
                scheduled_item_id=item.id,
                occurrence_date=date(2026, 10, 28),
                financial_document_id=second_bill.id,
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


def test_bill_amount_safe_integer():
    with pytest.raises(ValidationError):
        BillApprove(
            version=1,
            kind="invoice",
            supplier_name="Supplier",
            description="Description",
            total_minor=9_007_199_254_740_992,
            currency="PLN",
            declaration="payable",
        )


def test_approved_bill_requires_amount_and_currency_but_draft_can_be_incomplete():
    FinancialDocument(review="draft")
    with pytest.raises(ValidationError):
        BillApprove(version=1, kind="invoice", supplier_name="Supplier", description="Description")
