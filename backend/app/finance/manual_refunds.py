"""Explicit manual expense refunds, sharing the existing expense reversal ledger."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.finance.models import FinancialTransaction
from app.finance.queries import lock_accounts
from app.finance.schemas import ExpenseRefundCreate, PostingCreate, TransactionCreate
from app.finance.transactions import _create_transaction


async def create_manual_expense_refund(
    db: AsyncSession, user_id: uuid.UUID, data: ExpenseRefundCreate
) -> FinancialTransaction:
    accounts = await lock_accounts(db, user_id, {data.account_id})
    account = accounts.get(data.account_id)
    if account is None:
        raise ValueError("Account not found")
    if account.currency != "PLN":
        raise ValueError("Manual refunds currently require a PLN account")
    amount = data.amount_minor
    transaction = await _create_transaction(
        db,
        user_id,
        TransactionCreate(
            type="expense",
            source="manual",
            description=data.description,
            transaction_date=data.transaction_date,
            postings=[
                PostingCreate(
                    account_id=data.account_id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="credit",
                    is_budget_impact=account.is_budget_account,
                ),
                PostingCreate(
                    category_id=data.category_id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="debit",
                ),
            ],
        ),
        allow_manual_refund=True,
    )
    await log_event(
        db,
        user_id,
        "transaction",
        str(transaction.id),
        "create_expense_refund",
        new_state={
            "account_id": str(data.account_id),
            "category_id": str(data.category_id),
            "amount_minor": amount,
            "currency": "PLN",
            "transaction_date": data.transaction_date.isoformat(),
        },
    )
    return transaction
