"""Operator-only correction of confirmed, mislabelled Actual EUR history.

Not a normal account edit and deliberately not exposed through HTTP or AI tools.
The caller supplies approval/backup and owns the outer commit. No guessed FX.
"""

import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit.service import log_event
from app.finance.dates import _local_today
from app.finance.ledger_validation import _validate_posting_sum
from app.finance.models import (
    Account,
    Category,
    FinancialTransaction,
    LoanAgreement,
    LoanPaymentLink,
    Posting,
    ScheduledFinanceItem,
)
from app.finance.nbp_rates import NbpRateProvider
from app.finance.queries import lock_accounts


class CorrectionQuote(BaseModel):
    transaction_date: date
    effective_date: date
    rate: Decimal = Field(gt=0, lt=1_000_000, max_digits=12, decimal_places=6)
    source: Literal["nbp", "nbp_previous_business_day"]


class CorrectionPlan(BaseModel):
    user_id: uuid.UUID
    account_id: uuid.UUID
    before_hash: str
    transaction_ids: list[uuid.UUID]
    quotes: list[CorrectionQuote]

    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


def _state(account: Account, transactions: list[FinancialTransaction]) -> dict[str, Any]:
    def fields(row: Any) -> dict[str, Any]:
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}

    result = {
        "account": fields(account),
        "transactions": [fields(t) for t in transactions],
        "postings": [
            fields(p) for t in transactions for p in sorted(t.postings, key=lambda p: p.id)
        ],
    }
    return json.loads(json.dumps(result, default=str, sort_keys=True))


def _digest(state: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def _load(
    db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID, *, lock: bool = False
) -> tuple[Account, list[FinancialTransaction]]:
    if lock:
        account = (await lock_accounts(db, user_id, {account_id}, exclusive=True)).get(account_id)
    else:
        account = await db.scalar(
            select(Account).where(Account.id == account_id, Account.user_id == user_id)
        )
    if account is None:
        raise LookupError("Account not found")
    if account.source != "actual" or account.currency != "PLN":
        raise ValueError("Correction requires an Actual PLN account")
    if await db.scalar(
        select(ScheduledFinanceItem.id)
        .where(ScheduledFinanceItem.account_id == account.id)
        .limit(1)
    ):
        raise ValueError("Account has schedule dependencies")
    if await db.scalar(
        select(LoanAgreement.id)
        .where(
            (LoanAgreement.account_id == account.id)
            | (LoanAgreement.payment_account_id == account.id)
        )
        .limit(1)
    ):
        raise ValueError("Account has loan dependencies")
    statement = (
        select(FinancialTransaction)
        .where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.id.in_(
                select(Posting.transaction_id).where(Posting.account_id == account.id)
            ),
        )
        .order_by(FinancialTransaction.id)
        .options(selectinload(FinancialTransaction.postings))
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update()
    transactions = list((await db.scalars(statement)).all())
    count = await db.scalar(
        select(func.count()).select_from(Posting).where(Posting.account_id == account.id)
    )
    if not transactions or count != len(transactions):
        raise ValueError("History has foreign or ambiguous account postings")
    if await db.scalar(
        select(LoanPaymentLink.id)
        .where(LoanPaymentLink.transaction_id.in_([t.id for t in transactions]))
        .limit(1)
    ):
        raise ValueError("History has linked loan payments")
    category_ids: set[uuid.UUID] = set()
    for transaction in transactions:
        if (
            transaction.type not in ("income", "expense")
            or transaction.is_pending
            or transaction.date > _local_today()
            or len(transaction.postings) != 2
        ):
            raise ValueError("Only settled simple income/expense history can be corrected")
        account_legs = [
            p for p in transaction.postings if p.account_id == account.id and p.category_id is None
        ]
        category_legs = [
            p for p in transaction.postings if p.account_id is None and p.category_id is not None
        ]
        expected_direction = "credit" if transaction.type == "income" else "debit"
        if (
            len(account_legs) != 1
            or len(category_legs) != 1
            or account_legs[0].direction != expected_direction
            or category_legs[0].direction == expected_direction
        ):
            raise ValueError("History has unsupported posting shape")
        category_id = category_legs[0].category_id
        if category_id is None:
            raise ValueError("History has no category")
        category_ids.add(category_id)
        for posting in transaction.postings:
            if (
                posting.source_currency != "PLN"
                or posting.fx_rate != 1
                or posting.source_amount != posting.base_amount_pln
                or posting.source_amount <= 0
            ):
                raise ValueError("History is not uniformly mislabelled PLN at rate 1")
        _validate_posting_sum(transaction.postings, transaction.type)
    owned_categories = set(
        (
            await db.scalars(
                select(Category.id).where(
                    Category.user_id == user_id, Category.id.in_(category_ids)
                )
            )
        ).all()
    )
    if owned_categories != category_ids:
        raise ValueError("History references another owner's category")
    return account, transactions


async def preview_correction(
    db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID, provider: NbpRateProvider
) -> CorrectionPlan:
    account, transactions = await _load(db, user_id, account_id)
    quotes = []
    for transaction_date in sorted({t.date for t in transactions}):
        rate = await provider.get_rate("EUR", transaction_date)
        if (
            rate is None
            or rate.effective_date > transaction_date
            or rate.source not in {"nbp", "nbp_previous_business_day"}
        ):
            raise ValueError("Verified historical NBP rate unavailable")
        quotes.append(
            CorrectionQuote(
                transaction_date=transaction_date,
                effective_date=rate.effective_date,
                rate=Decimal(str(rate.rate)),
                source="nbp" if rate.source == "nbp" else "nbp_previous_business_day",
            )
        )
    return CorrectionPlan(
        user_id=user_id,
        account_id=account.id,
        before_hash=_digest(_state(account, transactions)),
        transaction_ids=[t.id for t in transactions],
        quotes=quotes,
    )


async def apply_correction(
    db: AsyncSession, user_id: uuid.UUID, plan: CorrectionPlan, *, approved_digest: str
) -> Account:
    if plan.user_id != user_id:
        raise LookupError("Correction owner not found")
    if not approved_digest or approved_digest != plan.digest():
        raise ValueError("Exact correction plan approval is required")
    # Approval is an independent caller-supplied pin, not proof of an exchange
    # rate. Re-read the controlled official source before taking write locks.
    provider = NbpRateProvider()
    try:
        for quote in plan.quotes:
            official = await provider.get_rate("EUR", quote.transaction_date)
            if official is None or (
                Decimal(str(official.rate)),
                official.effective_date,
                official.source,
            ) != (quote.rate, quote.effective_date, quote.source):
                raise ValueError("Approved NBP quote differs from the official historical rate")
    finally:
        await provider.close()
    async with db.begin_nested():
        account, transactions = await _load(db, user_id, plan.account_id, lock=True)
        before = _state(account, transactions)
        if (
            _digest(before) != plan.before_hash
            or [t.id for t in transactions] != plan.transaction_ids
        ):
            raise ValueError("History changed since preview")
        quotes = {q.transaction_date: q for q in plan.quotes}
        if len(quotes) != len(plan.quotes) or set(quotes) != {t.date for t in transactions}:
            raise ValueError("Missing or duplicate NBP quote")
        for quote in plan.quotes:
            if quote.effective_date > quote.transaction_date or (
                quote.source == "nbp" and quote.effective_date != quote.transaction_date
            ):
                raise ValueError("Invalid historical NBP quote date")
        account.currency = "EUR"
        for transaction in transactions:
            quote = quotes[transaction.date]
            for posting in transaction.postings:
                base = NbpRateProvider().calculate_base_amount(
                    posting.source_amount, float(quote.rate)
                )
                if not 0 < base <= 9_007_199_254_740_991:
                    raise ValueError("Corrected amount outside safe API range")
                posting.source_currency = "EUR"
                posting.base_amount_pln = base
                posting.fx_rate = float(quote.rate)
                posting.fx_rate_source = f"{quote.source}:{quote.effective_date.isoformat()}"
            _validate_posting_sum(transaction.postings, transaction.type)
        await db.flush()
        await db.refresh(account)
        for transaction in transactions:
            for posting in transaction.postings:
                await db.refresh(posting)
        await log_event(
            db,
            user_id,
            "account",
            str(account.id),
            "correct_source_currency",
            old_state=before,
            new_state=_state(account, transactions),
            performed_by="human",
        )
        return account
