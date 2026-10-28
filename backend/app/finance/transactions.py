"""Ledger mutations and FX conversion; transaction boundaries belong to callers."""

import uuid
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.finance.dates import _local_today
from app.finance.ledger_validation import _validate_posting_sum, _validate_transaction_postings
from app.finance.models import FinancialTransaction, LoanPaymentLink, Posting
from app.finance.nbp_rates import NbpRateProvider
from app.finance.queries import get_accounts
from app.finance.schemas import ExchangeCreate, PostingCreate, TransactionCreate, TransactionUpdate
from app.work.service import validate_project_reference


async def create_transaction(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: TransactionCreate,
    *,
    allow_category_reversal: bool = False,
    allow_inactive_accounts: bool = False,
) -> FinancialTransaction:
    # Only trusted import code explicitly opts into preserving source-category
    # reversals. Client-controlled `source` never disables validation.
    if allow_category_reversal and data.source != "actual":
        raise ValueError("Category reversals require the explicit Actual import path")
    if allow_inactive_accounts and data.source != "actual":
        raise ValueError("Inactive account history requires the explicit Actual import path")
    _validate_posting_sum(data.postings, data.type)
    await _validate_transaction_postings(
        db,
        user_id,
        data.postings,
        data.type,
        allow_category_reversal=allow_category_reversal,
        allow_inactive_accounts=allow_inactive_accounts,
    )
    await validate_project_reference(db, user_id, data.project_id)

    txn = FinancialTransaction(
        user_id=user_id,
        date=data.transaction_date or _local_today(),
        description=data.description,
        type=data.type,
        is_pending=data.is_pending,
        project_id=data.project_id,
        source=data.source,
    )
    db.add(txn)
    await db.flush()

    for p_data in data.postings:
        posting = Posting(
            transaction_id=txn.id,
            account_id=p_data.account_id,
            category_id=p_data.category_id,
            source_amount=p_data.source_amount,
            source_currency=p_data.source_currency.upper(),
            base_amount_pln=p_data.base_amount_pln,
            fx_rate=p_data.fx_rate,
            fx_rate_source=p_data.fx_rate_source,
            direction=p_data.direction,
            is_budget_impact=p_data.is_budget_impact,
        )
        db.add(posting)

    await db.flush()

    result = await db.execute(
        select(FinancialTransaction)
        .options(selectinload(FinancialTransaction.postings))
        .where(FinancialTransaction.id == txn.id)
    )
    return result.scalar_one()


async def create_exchange_transaction(
    db: AsyncSession, user_id: uuid.UUID, data: ExchangeCreate
) -> FinancialTransaction:
    accounts = {account.id: account for account in await get_accounts(db, user_id)}

    from_account = accounts.get(data.from_account_id)
    to_account = accounts.get(data.to_account_id)
    if from_account is None or to_account is None:
        raise ValueError("Exchange account not found")
    if not from_account.is_active or not to_account.is_active:
        raise ValueError("Exchange account is not active")
    if from_account.id == to_account.id:
        raise ValueError("Exchange accounts must be different")

    from_currency = str(from_account.currency).upper()
    to_currency = str(to_account.currency).upper()
    if from_currency == to_currency:
        raise ValueError("Exchange accounts must have different currencies")
    if from_currency != "PLN" and to_currency != "PLN":
        raise ValueError("Cross-currency exchange is not supported")

    foreign_currency = from_currency if to_currency == "PLN" else to_currency
    effective_date = data.transaction_date or _local_today()

    if data.fx_rate is not None:
        rate = Decimal(str(data.fx_rate))
        rate_source = "manual"
    else:
        provider = NbpRateProvider()
        try:
            quote = await provider.get_rate(foreign_currency, effective_date)
        finally:
            await provider.close()
        if quote is None:
            raise ValueError(f"No FX rate available for {foreign_currency} on {effective_date}")
        rate = Decimal(str(quote.rate))
        rate_source = quote.source

    fx_rate_from = Decimal(1) if from_currency == "PLN" else rate
    fx_rate_to = Decimal(1) if to_currency == "PLN" else rate

    base = int(
        (Decimal(data.from_amount) * fx_rate_from).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
    )
    to_amount = int((Decimal(base) / fx_rate_to).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))

    return await create_transaction(
        db,
        user_id,
        TransactionCreate(
            transaction_date=effective_date,
            description=data.description,
            type="exchange",
            postings=[
                PostingCreate(
                    account_id=from_account.id,
                    source_amount=data.from_amount,
                    source_currency=from_currency,
                    base_amount_pln=base,
                    fx_rate=float(fx_rate_from),
                    fx_rate_source=rate_source,
                    direction="debit",
                ),
                PostingCreate(
                    account_id=to_account.id,
                    source_amount=to_amount,
                    source_currency=to_currency,
                    base_amount_pln=base,
                    fx_rate=float(fx_rate_to),
                    fx_rate_source=rate_source,
                    direction="credit",
                ),
            ],
        ),
    )


async def update_transaction(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID, data: TransactionUpdate
) -> FinancialTransaction | None:
    txn = (
        await db.execute(
            select(FinancialTransaction)
            .where(
                FinancialTransaction.id == transaction_id, FinancialTransaction.user_id == user_id
            )
            .options(selectinload(FinancialTransaction.postings))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if txn is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    if ("transaction_date" in update_data and update_data["transaction_date"] != txn.date) or (
        "is_pending" in update_data and update_data["is_pending"] != txn.is_pending
    ):
        linked = await db.scalar(
            select(LoanPaymentLink.id)
            .where(LoanPaymentLink.transaction_id == transaction_id)
            .limit(1)
        )
        if linked is not None:
            raise ValueError("Cannot change date or pending status of a linked loan payment")
    if any(
        update_data.get(key, True) is None
        for key in ("transaction_date", "description", "is_pending")
    ):
        raise ValueError("Transaction date, description and is_pending cannot be null")
    if "project_id" in update_data:
        await validate_project_reference(db, user_id, update_data["project_id"])
    if "transaction_date" in update_data:
        update_data["date"] = update_data.pop("transaction_date")
    for key, value in update_data.items():
        setattr(txn, key, value)
    await db.flush()
    await db.refresh(txn, attribute_names=["updated_at"])
    return txn


async def delete_transaction(
    db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID
) -> bool:
    txn = (
        await db.execute(
            select(FinancialTransaction)
            .where(
                FinancialTransaction.id == transaction_id, FinancialTransaction.user_id == user_id
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if txn is None:
        return False
    if (
        await db.scalar(
            select(LoanPaymentLink.id)
            .where(LoanPaymentLink.transaction_id == transaction_id)
            .limit(1)
        )
        is not None
    ):
        raise ValueError("Cannot delete a linked loan payment")
    await db.delete(txn)
    await db.flush()
    return True
