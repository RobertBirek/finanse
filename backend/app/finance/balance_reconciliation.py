"""Read-only comparison of a bank statement with the booked account balance."""

from datetime import date
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.finance.models import Account, FinancialTransaction, Posting
from app.finance.schemas import BalanceReconciliationResponse


def compare_balances(ledger_minor: int, statement_minor: int) -> int:
    return statement_minor - ledger_minor


def balance_on_day_statement(owner: UUID, account_id: UUID, day: date) -> Select[tuple[str, int]]:
    # The ledger stores its effective booking day in FinancialTransaction.date.
    # Use the same account-side signs as the account balance read.
    booked = (
        select(
            func.sum(
                case(
                    (Posting.direction == "credit", Posting.source_amount),
                    else_=-Posting.source_amount,
                )
            )
        )
        .join(FinancialTransaction, FinancialTransaction.id == Posting.transaction_id)
        .where(
            Posting.account_id == Account.id,
            FinancialTransaction.user_id == owner,
            FinancialTransaction.date <= day,
            FinancialTransaction.is_pending.is_(False),
        )
        .correlate(Account)
        .scalar_subquery()
    )
    return select(Account.currency, func.coalesce(booked, 0)).where(
        Account.id == account_id, Account.user_id == owner
    )


async def reconcile_balance(
    db: AsyncSession, owner: UUID, account_id: UUID, day: date, statement_minor: int
) -> BalanceReconciliationResponse | None:
    row = (await db.execute(balance_on_day_statement(owner, account_id, day))).one_or_none()
    if row is None:
        return None
    currency, balance = row
    ledger = int(balance)
    return BalanceReconciliationResponse(
        day=day,
        currency=currency,
        ledger_minor=str(ledger),
        statement_minor=str(statement_minor),
        difference_minor=str(compare_balances(ledger, statement_minor)),
    )
