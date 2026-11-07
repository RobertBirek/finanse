"""Card facts, estimates and allocations are deliberately separate from postings."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.finance.credit_card_math import MAX_MONEY

Money = Annotated[int, Field(ge=0, le=MAX_MONEY, strict=True)]
PositiveMoney = Annotated[int, Field(gt=0, le=MAX_MONEY, strict=True)]
APR = Annotated[Decimal, Field(ge=0, le=100, max_digits=7, decimal_places=4, allow_inf_nan=False)]


class CardInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CardConfig(CardInput):
    limit_pln: PositiveMoney
    apr: APR
    cycle_close_day: int = Field(ge=1, le=31, strict=True)
    due_day: int = Field(ge=1, le=31, strict=True)
    grace_days: int = Field(ge=0, le=366, strict=True)
    expected_version: int = Field(ge=0, strict=True)


class StatementCreate(CardInput):
    request_id: uuid.UUID
    period_start: date
    period_end: date
    due_date: date
    debt_pln: Money
    minimum_pln: Money
    source_reference: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def valid_period(self) -> "StatementCreate":
        if not self.period_start <= self.period_end < self.due_date:
            raise ValueError("Statement dates must be start <= end < due")
        if self.minimum_pln > self.debt_pln:
            raise ValueError("Minimum exceeds statement debt")
        return self


class PlanCreate(CardInput):
    request_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    source_transaction_id: uuid.UUID
    principal_pln: PositiveMoney
    apr: APR
    count: int = Field(ge=1, le=600, strict=True)
    first_due: date
    fees_pln: Money = 0


class InstallmentInput(CardInput):
    number: int = Field(ge=1, le=600, strict=True)
    due_date: date
    principal_pln: PositiveMoney
    interest_pln: Money
    fees_pln: Money

    @model_validator(mode="after")
    def safe_total(self) -> "InstallmentInput":
        if self.principal_pln + self.interest_pln + self.fees_pln > MAX_MONEY:
            raise ValueError("Installment total exceeds safe integer limit")
        return self


class BankSchedule(CardInput):
    expected_version: int = Field(ge=1, strict=True)
    installments: list[InstallmentInput] = Field(min_length=1, max_length=600)


class AllocationCreate(CardInput):
    request_id: uuid.UUID
    transaction_id: uuid.UUID
    statement_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    amount_pln: PositiveMoney
    principal_pln: Money = 0
    interest_pln: Money = 0
    fees_pln: Money = 0

    @model_validator(mode="after")
    def valid_target(self) -> "AllocationCreate":
        if (self.statement_id is None) == (self.plan_id is None):
            raise ValueError("Choose exactly one statement or plan")
        components = self.principal_pln + self.interest_pln + self.fees_pln
        if (self.plan_id and components != self.amount_pln) or (self.statement_id and components):
            raise ValueError(
                "Plan allocation components must match amount; statements have no components"
            )
        return self


class ChargeCreate(CardInput):
    request_id: uuid.UUID
    kind: Literal["interest", "fee", "interest_refund", "fee_refund"]
    amount_pln: PositiveMoney
    description: str = Field(min_length=1, max_length=300)
    booking_date: date
    category_id: uuid.UUID
    existing_transaction_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None


class InterestEstimate(CardInput):
    principal_pln: Money
    apr: APR
    days: int = Field(ge=0, le=3660, strict=True)
