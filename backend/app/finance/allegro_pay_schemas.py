"""Validated Allegro Pay commands."""

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_AMOUNT = 9_007_199_254_740_991


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: uuid.UUID
    limit_pln: int | None = Field(default=None, strict=True, gt=0, le=MAX_AMOUNT)


class InstallmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    due_date: dt.date
    principal_pln: int = Field(strict=True, ge=0, le=MAX_AMOUNT)
    interest_pln: int = Field(strict=True, ge=0, le=MAX_AMOUNT)
    fees_pln: int = Field(strict=True, ge=0, le=MAX_AMOUNT)

    @model_validator(mode="after")
    def valid_total(self) -> "InstallmentInput":
        if not 0 < self.principal_pln + self.interest_pln + self.fees_pln <= MAX_AMOUNT:
            raise ValueError("Nieprawidłowa kwota raty")
        return self


class PurchaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    request_id: uuid.UUID
    purchase_date: dt.date
    principal_pln: int = Field(strict=True, gt=0, le=MAX_AMOUNT)
    transaction_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    installments: list[InstallmentInput] = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def valid_purchase(self) -> "PurchaseInput":
        if (self.transaction_id is None) == (self.category_id is None):
            raise ValueError("Wybierz istniejący wydatek albo kategorię nowego wydatku")
        if sum(item.principal_pln for item in self.installments) != self.principal_pln:
            raise ValueError("Suma kapitału rat musi odpowiadać kwocie zakupu")
        return self


class AllocationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    installment_id: uuid.UUID
    amount_pln: int = Field(strict=True, gt=0, le=MAX_AMOUNT)


class PaymentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transaction_id: uuid.UUID
    allocations: list[AllocationInput] = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def unique_installments(self) -> "PaymentInput":
        if len({item.installment_id for item in self.allocations}) != len(self.allocations):
            raise ValueError("Rata może wystąpić tylko raz")
        if sum(item.amount_pln for item in self.allocations) > MAX_AMOUNT:
            raise ValueError("Suma przekracza zakres kwoty")
        return self
