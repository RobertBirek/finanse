"""Server-only adapter for frozen actual bank legs; never a public request schema."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.models import FinancialTransaction
from app.finance.schemas import PostingCreate, TransactionCreate
from app.finance.transactions import _create_transaction


class BankPostingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    source_amount: int = Field(strict=True, gt=0, le=9007199254740991)
    source_currency: Literal["PLN", "EUR", "USD"]
    base_amount_pln: int = Field(strict=True, gt=0, le=9007199254740991)
    fx_rate: Decimal = Field(gt=0, lt=1000000, allow_inf_nan=False)
    fx_rate_source: str = Field(min_length=1, max_length=50)
    direction: Literal["debit", "credit"]


class BankTransactionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["expense", "income", "expense_refund", "transfer", "exchange"]
    booking_date: date
    purchase_date: date | None = None
    description: str = Field(min_length=1)
    postings: tuple[BankPostingInput, ...] = Field(min_length=2)


async def create_bank_transaction(
    db: AsyncSession, owner: uuid.UUID, data: BankTransactionInput
) -> FinancialTransaction:
    if data.kind in {"transfer", "exchange"}:
        if len(data.postings) != 2 or any(
            posting.account_id is None or posting.category_id is not None
            for posting in data.postings
        ):
            raise ValueError("Bank transfers require exactly two account postings")
        first, second = data.postings
        if first.account_id == second.account_id or [first.direction, second.direction] != [
            "debit",
            "credit",
        ]:
            raise ValueError("Bank transfers require distinct outgoing/incoming accounts")
        if data.kind == "transfer" and (
            first.source_currency != second.source_currency
            or first.source_amount != second.source_amount
        ):
            raise ValueError("Transfer must preserve actual amounts in the same currency")
        if data.kind == "exchange" and first.source_currency == second.source_currency:
            raise ValueError("Exchange requires two distinct currencies")
    transaction = TransactionCreate(
        transaction_date=data.booking_date,
        description=data.description,
        type="expense" if data.kind == "expense_refund" else data.kind,
        source="bank_import",
        postings=[PostingCreate(**posting.model_dump()) for posting in data.postings],
    )
    return await _create_transaction(
        db,
        owner,
        transaction,
        allow_bank_refund=data.kind == "expense_refund",
        import_dates=(data.purchase_date, data.booking_date),
    )
