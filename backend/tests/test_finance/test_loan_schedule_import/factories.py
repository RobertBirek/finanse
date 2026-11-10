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
