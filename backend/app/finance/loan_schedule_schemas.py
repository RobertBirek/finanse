"""Strict command boundary for plan activation, not financial postings."""

import uuid
from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.finance.loan_schedule_diff import ScheduleDiff
from app.finance.loan_schemas import LoanCreate


class ScheduleTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    loan_id: uuid.UUID | None = None
    new_loan: LoanCreate | None = None

    @model_validator(mode="after")
    def exactly_one(self) -> Self:
        if (self.loan_id is None) == (self.new_loan is None):
            raise ValueError("Wybierz istniejący kredyt albo jawnie podaj nową umowę.")
        return self


class SchedulePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, strict=True)
    source_id: uuid.UUID
    target: ScheduleTarget
    acknowledgements: list[str] = Field(default_factory=list)


class ScheduleActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: uuid.UUID
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ScheduleCommitResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_id: uuid.UUID
    batch_id: uuid.UUID
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    loan_id: uuid.UUID
    revision_id: uuid.UUID
    reused_ids: list[uuid.UUID]
    new_ids: list[uuid.UUID]
    superseded_ids: list[uuid.UUID]
    ledger_changed: Literal[False] = False


class SchedulePreviewDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    batch_id: uuid.UUID
    version: int
    request_hash: str
    source_revision_id: uuid.UUID
    target: ScheduleTarget
    cutover_date: date
    loan_fingerprint: str
    diff: ScheduleDiff
    ledger_effect: Literal["none"] = "none"
    bank_effective_date: date | None = None


class ScheduleRevisionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    loan_id: uuid.UUID
    ordinal: int
    kind: Literal["manual_baseline", "bank_import"]
    state: Literal["active", "superseded"]
    previous_revision_id: uuid.UUID | None
    source_revision_id: uuid.UUID | None
    receipt_id: uuid.UUID
    bank_effective_date: date | None
    activated_on: date
    cutover_date: date
    document_id: uuid.UUID | None = None
    original_name: str | None = None
    batch_id: uuid.UUID | None = None


class ScheduleMembershipDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    installment_id: uuid.UUID
    bank_number: int | None
    source_row_id: uuid.UUID | None
    due_date: date
    principal_pln: int
    interest_pln: int
    fees_pln: int
    balance_after_pln: int | None


class ScheduleRevisionDetailDTO(ScheduleRevisionDTO):
    installments: list[ScheduleMembershipDTO]
