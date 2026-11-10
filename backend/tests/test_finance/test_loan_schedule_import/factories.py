"""Synthetic plan state, never real Q7 or bank data."""

import hashlib
import json
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base
from app.finance.entities import create_account
from app.finance.loan_schemas import LoanCreate, LoanInstallmentCreate
from app.finance.loans import create_loan, create_loan_installment
from app.finance.models import FinanceCommandReceipt, LoanAgreement, LoanInstallment
from app.finance.schemas import AccountCreate


async def financial_history_snapshot(db: AsyncSession) -> dict[str, str]:
    result = {}
    for name in [
        "accounts",
        "financial_transactions",
        "postings",
        "actual_import_mappings",
        "loan_payment_links",
    ]:
        rows = [
            json.dumps(dict(row), sort_keys=True, default=str)
            for row in (await db.execute(select(Base.metadata.tables[name]))).mappings()
        ]
        result[name] = hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()
    return result


async def legacy_loan(
    db: AsyncSession, owner_id: uuid.UUID
) -> tuple[LoanAgreement, LoanInstallment, FinanceCommandReceipt]:
    payer = await create_account(
        db, owner_id, AccountCreate(name="Synthetic payment", type="checking", currency="PLN")
    )
    debt = await create_account(
        db, owner_id, AccountCreate(name="Synthetic debt", type="credit", currency="PLN")
    )
    created = await create_loan(
        db,
        owner_id,
        LoanCreate(name="Synthetic loan", account_id=debt.id, payment_account_id=payer.id),
    )
    detail = await create_loan_installment(
        db,
        owner_id,
        created.id,
        LoanInstallmentCreate(
            number=1, due_date=date(2026, 12, 1), principal_pln=10000, interest_pln=500, fees_pln=0
        ),
    )
    loan = await db.get(LoanAgreement, created.id)
    installment = await db.get(LoanInstallment, detail.id)
    assert loan is not None and installment is not None
    receipt = FinanceCommandReceipt(
        user_id=owner_id,
        action="loan_schedule.activate",
        key=uuid.uuid4().hex,
        request_hash="a" * 64,
        response_json={},
    )
    db.add(receipt)
    await db.flush()
    return loan, installment, receipt


async def schedule_version(db, owner_id, loan, receipt, *, bank=False):
    """Synthetic version only; used to exercise projection and immutability guards."""
    from app.documents.models import Document
    from app.finance.imports.models import ImportBatch, ImportRevision, ImportSource
    from app.finance.loan_schedule_models import LoanScheduleRevision

    source_revision_id = None
    if bank:
        document = Document(
            user_id=owner_id,
            filename="synthetic-schedule.pdf",
            original_name="synthetic-schedule.pdf",
            mime_type="application/pdf",
            sha256_hash=uuid.uuid4().hex * 2,
            size_bytes=1,
            storage_path="/test/synthetic-schedule.pdf",
            status="done",
            processing_method="bank_import",
        )
        batch = ImportBatch(user_id=owner_id, kind="loan_schedule")
        db.add_all([document, batch])
        await db.flush()
        source = ImportSource(
            user_id=owner_id, batch_id=batch.id, document_id=document.id, kind="loan_schedule"
        )
        db.add(source)
        await db.flush()
        revision = ImportRevision(
            user_id=owner_id,
            batch_id=batch.id,
            source_id=source.id,
            number=1,
            source_sha256=document.sha256_hash,
        )
        db.add(revision)
        await db.flush()
        source_revision_id = revision.id
    revision = LoanScheduleRevision(
        user_id=owner_id,
        loan_id=loan.id,
        receipt_id=receipt.id,
        ordinal=1,
        kind="bank_import" if bank else "manual_baseline",
        state="active",
        source_revision_id=source_revision_id,
        activated_on=date(2026, 11, 10),
        cutover_date=date(2026, 11, 10),
    )
    db.add(revision)
    await db.flush()
    loan.active_schedule_revision_id = revision.id
    await db.flush()
    return revision


async def payment_transfer(db, owner_id, loan, amount=100):
    from app.finance.schemas import PostingCreate, TransactionCreate
    from app.finance.transactions import create_transaction

    return await create_transaction(
        db,
        owner_id,
        TransactionCreate(
            transaction_date="2020-01-01",
            description="Synthetic repayment",
            type="transfer",
            postings=[
                PostingCreate(
                    account_id=loan.payment_account_id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="debit",
                ),
                PostingCreate(
                    account_id=loan.account_id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="credit",
                ),
            ],
        ),
    )
