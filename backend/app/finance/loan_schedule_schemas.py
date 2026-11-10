"""Strict command boundary for plan activation, not financial postings."""

import uuid
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
