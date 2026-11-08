"""Immutable normalized source values, never instructions to mutate the ledger."""

import datetime as dt
from dataclasses import dataclass
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    field_validator,
    model_validator,
)

MAX_MINOR_UNITS = 9_007_199_254_740_991
Bank = Literal["velo", "ing", "revolut"]
Currency = Literal["PLN", "EUR", "USD"]
ImportKind = Literal["statement", "loan_schedule"]
MinorUnits = Annotated[int, Field(strict=True, ge=-MAX_MINOR_UNITS, le=MAX_MINOR_UNITS)]
NonnegativeMinorUnits = Annotated[int, Field(strict=True, ge=0, le=MAX_MINOR_UNITS)]
PositiveMinorUnits = Annotated[int, Field(strict=True, gt=0, le=MAX_MINOR_UNITS)]


class SourceValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _calendar_date(value: object) -> dt.date | None:
    if value is None:
        return None
    if type(value) is dt.date:
        return value
    if isinstance(value, str):
        parsed = dt.date.fromisoformat(value)
        if parsed.isoformat() == value:
            return parsed
    raise ValueError("Source date must be an ISO calendar date")


class SourcePosition(SourceValue):
    page: Annotated[int, Field(strict=True, ge=1)] | None = None
    line: Annotated[int, Field(strict=True, ge=1)]
    section: str | None = None


class Check(SourceValue):
    code: str = Field(min_length=1)
    required: StrictBool
    result: Literal["passed", "failed", "unavailable"]
    expected: MinorUnits | None = None
    actual: MinorUnits | None = None


class StatementRow(SourceValue):
    key: str = Field(min_length=1)
    position: SourcePosition
    booking_date: dt.date | None
    operation_date: dt.date | None = None
    started_at: str | None = None
    completed_at: str | None = None
    description: str
    amount: MinorUnits
    fee: MinorUnits
    currency: Currency
    state: Literal["posted", "pending", "reverted", "cancelled", "unknown"]
    balance_after: MinorUnits | None = None
    bank_reference: str | None = None
    raw: dict[str, JsonValue]

    _dates = field_validator("booking_date", "operation_date", mode="before")(_calendar_date)

    @model_validator(mode="after")
    def validate_posted_source(self) -> Self:
        if self.state == "posted" and self.booking_date is None:
            raise ValueError("A posted source row requires its booking date")
        if abs(self.amount + self.fee) > MAX_MINOR_UNITS:
            raise ValueError("Main component exceeds the API amount limit")
        return self


class ParsedStatement(SourceValue):
    kind: Literal["statement"] = "statement"
    bank: Bank
    layout: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    account_reference: str | None
    currency: Currency
    period_start: dt.date
    period_end: dt.date
    opening: MinorUnits | None
    closing: MinorUnits | None
    rows: list[StatementRow]
    checks: list[Check]
    warnings: list[str]
    card_header: dict[str, JsonValue] | None = None

    _dates = field_validator("period_start", "period_end", mode="before")(_calendar_date)

    @model_validator(mode="after")
    def validate_source_boundaries(self) -> Self:
        if self.period_end < self.period_start:
            raise ValueError("Statement period ends before it starts")
        if len({row.key for row in self.rows}) != len(self.rows):
            raise ValueError("Source row keys must be unique within one revision")
        if any(row.currency != self.currency for row in self.rows):
            raise ValueError("Statement rows must belong to the source account currency")
        return self


class ScheduleRow(SourceValue):
    bank_number: Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]
    due_date: dt.date
    principal: NonnegativeMinorUnits
    interest: NonnegativeMinorUnits
    fees: NonnegativeMinorUnits
    total: PositiveMinorUnits
    balance_after: NonnegativeMinorUnits | None
    position: SourcePosition

    _date = field_validator("due_date", mode="before")(_calendar_date)

    @model_validator(mode="after")
    def validate_components(self) -> Self:
        if self.principal + self.interest + self.fees != self.total:
            raise ValueError("Schedule total must equal principal, interest and fees")
        return self


class ParsedSchedule(SourceValue):
    kind: Literal["loan_schedule"] = "loan_schedule"
    bank: Bank
    layout: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    loan_reference: str | None
    effective_date: dt.date | None
    currency: Literal["PLN"] = "PLN"
    rows: list[ScheduleRow]
    checks: list[Check]
    warnings: list[str]
    complete_tail: StrictBool

    _date = field_validator("effective_date", mode="before")(_calendar_date)

    @model_validator(mode="after")
    def validate_row_identity(self) -> Self:
        if self.complete_tail and not self.rows:
            raise ValueError("A complete remaining schedule must contain its table")
        if len({row.bank_number for row in self.rows}) != len(self.rows):
            raise ValueError("Bank row numbers must be unique within one revision")
        return self


ParsedImport = Annotated[ParsedStatement | ParsedSchedule, Field(discriminator="kind")]


@dataclass(frozen=True)
class ParserInput:
    content: bytes
    pages: tuple[str, ...] | None
    mime_type: str
    sha256: str


@dataclass(frozen=True)
class ImportFailure:
    code: str
    retryable: bool
