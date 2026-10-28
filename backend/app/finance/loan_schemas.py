import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_AMOUNT = 9_007_199_254_740_991


class LoanCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    account_id: uuid.UUID
    payment_account_id: uuid.UUID


class LoanUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None


class LoanInstallmentCreate(BaseModel):
    number: int = Field(gt=0, le=2_147_483_647, strict=True)
    due_date: dt.date
    principal_pln: int = Field(ge=0, le=MAX_AMOUNT, strict=True)
    interest_pln: int = Field(ge=0, le=MAX_AMOUNT, strict=True)
    fees_pln: int = Field(ge=0, le=MAX_AMOUNT, strict=True)

    @model_validator(mode="after")
    def validate_total(self) -> "LoanInstallmentCreate":
        total = self.principal_pln + self.interest_pln + self.fees_pln
        if total == 0 or total > MAX_AMOUNT:
            raise ValueError("Installment total must be between 1 and the API amount limit")
        return self


class LoanInstallmentUpdate(BaseModel):
    number: int | None = Field(default=None, gt=0, le=2_147_483_647, strict=True)
    due_date: dt.date | None = None
    principal_pln: int | None = Field(default=None, ge=0, le=MAX_AMOUNT, strict=True)
    interest_pln: int | None = Field(default=None, ge=0, le=MAX_AMOUNT, strict=True)
    fees_pln: int | None = Field(default=None, ge=0, le=MAX_AMOUNT, strict=True)


class LoanPaymentCreate(BaseModel):
    transaction_id: uuid.UUID


class LoanPaymentResponse(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    transaction_date: dt.date
    amount_pln: int


class LoanInstallmentResponse(BaseModel):
    id: uuid.UUID
    number: int
    due_date: dt.date
    principal_pln: int
    interest_pln: int
    fees_pln: int
    total_pln: int
    paid_pln: int
    remaining_pln: int
    payment_status: Literal["unpaid", "partial", "paid"]
    payments: list[LoanPaymentResponse]


class LoanResponse(BaseModel):
    id: uuid.UUID
    name: str
    account_id: uuid.UUID
    payment_account_id: uuid.UUID
    is_active: bool
    currency: Literal["PLN"] = "PLN"
    ledger_balance_pln: int
    planned_principal_pln: int
    planned_interest_pln: int
    planned_fees_pln: int
    total_planned_pln: int
    paid_pln: int
    remaining_pln: int
    requires_accounting_review: Literal[True] = True


class LoanDetailResponse(LoanResponse):
    installments: list[LoanInstallmentResponse]


class LoanPaymentCandidate(BaseModel):
    transaction_id: uuid.UUID
    transaction_date: dt.date
    description: str
    amount_pln: int


class LoanPaymentCandidatesResponse(BaseModel):
    items: list[LoanPaymentCandidate]
    total: int
    limit: int
    offset: int
