import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator

BillKind = Literal["invoice", "receipt"]
BillReview = Literal["draft", "approved", "rejected"]
PaymentDeclaration = Literal["unknown", "payable", "declared_paid"]
BillLifecycle = Literal["active", "archived", "cancelled"]
ReconciliationState = Literal["none", "partial", "full"]

MAX_SAFE_MINOR = 9_007_199_254_740_991


class MutationContext(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    performed_by: str = "human"


class BillApprove(BaseModel):
    version: StrictInt = Field(ge=1)
    kind: BillKind
    supplier_name: str = Field(min_length=1, max_length=200)
    supplier_tax_id: str | None = Field(default=None, max_length=64)
    number: str | None = Field(default=None, max_length=100)
    issue_date: dt.date | None = None
    sale_date: dt.date | None = None
    due_date: dt.date | None = None
    payee_iban: str | None = Field(default=None, max_length=34)
    category_id: uuid.UUID | None = None
    payment_account_id: uuid.UUID | None = None
    description: str = Field(min_length=1)
    total_minor: StrictInt = Field(gt=0, le=MAX_SAFE_MINOR)
    currency: Literal["PLN", "EUR", "USD"]
    declaration: PaymentDeclaration | None = None
    duplicate_decision: Literal["separate"] | None = None

    @model_validator(mode="after")
    def default_receipt_declaration(self) -> "BillApprove":
        if self.declaration is None:
            self.declaration = "declared_paid" if self.kind == "receipt" else "unknown"
        return self


class BillUpdate(BaseModel):
    expected_version: StrictInt = Field(ge=1)
    kind: BillKind | None = None
    supplier_name: str | None = Field(default=None, min_length=1, max_length=200)
    supplier_tax_id: str | None = Field(default=None, max_length=64)
    number: str | None = Field(default=None, max_length=100)
    issue_date: dt.date | None = None
    sale_date: dt.date | None = None
    due_date: dt.date | None = None
    payee_iban: str | None = Field(default=None, max_length=34)
    category_id: uuid.UUID | None = None
    payment_account_id: uuid.UUID | None = None
    description: str | None = Field(default=None, min_length=1)
    total_minor: StrictInt | None = Field(default=None, gt=0, le=MAX_SAFE_MINOR)
    currency: Literal["PLN", "EUR", "USD"] | None = None
    declaration: PaymentDeclaration | None = None


class DuplicateCandidate(BaseModel):
    id: uuid.UUID
    reasons: list[str]


class BillLifecycleUpdate(BaseModel):
    expected_version: StrictInt = Field(ge=1)
    lifecycle: BillLifecycle


class AllocationCreate(BaseModel):
    version: StrictInt = Field(ge=1)
    posting_id: uuid.UUID
    amount_minor: StrictInt = Field(gt=0, le=MAX_SAFE_MINOR)
    confirm_recurring_conflict: Literal[True] | None = None


class BillPaymentCreate(BaseModel):
    version: StrictInt = Field(ge=1)
    account_id: uuid.UUID
    category_id: uuid.UUID
    payment_date: dt.date
    amount_minor: StrictInt = Field(gt=0, le=MAX_SAFE_MINOR)
    description: str = Field(min_length=1)
    confirm_new_payment: Literal[True]


class CoverageDecision(BaseModel):
    version: StrictInt = Field(ge=1)
    choice: Literal["replace", "separate"]
    scheduled_item_id: uuid.UUID | None = None
    occurrence_date: dt.date | None = None

    @model_validator(mode="after")
    def require_occurrence_for_replacement(self) -> "CoverageDecision":
        if self.choice == "replace" and (
            self.scheduled_item_id is None or self.occurrence_date is None
        ):
            raise ValueError("replace requires scheduled_item_id and occurrence_date")
        return self


class AllocationResponse(BaseModel):
    posting_id: uuid.UUID
    amount_minor: int


class SourceResponse(BaseModel):
    document_id: uuid.UUID


class CoverageResponse(BaseModel):
    scheduled_item_id: uuid.UUID
    occurrence_date: dt.date
    choice: Literal["replace", "separate"]
    source_lifecycle: BillLifecycle


class CoverageCandidate(BaseModel):
    scheduled_item_id: uuid.UUID
    occurrence_date: dt.date
    name: str


class BillResponse(BaseModel):
    id: uuid.UUID
    kind: BillKind | None
    supplier_name: str | None
    supplier_tax_id: str | None
    number: str | None
    issue_date: dt.date | None
    sale_date: dt.date | None
    due_date: dt.date | None
    payee_iban: str | None
    description: str | None
    category_id: uuid.UUID | None
    payment_account_id: uuid.UUID | None
    total_minor: int | None
    currency: Literal["PLN", "EUR", "USD"] | None
    declaration: PaymentDeclaration
    lifecycle: BillLifecycle
    review: BillReview
    version: int
    paid_minor: int
    remaining_minor: int
    reconciliation: ReconciliationState
    sources: list[SourceResponse]
    allocations: list[AllocationResponse]
    extraction_revision_id: uuid.UUID | None = None
    coverage: CoverageResponse | None = None
    forecast_exclusion_reasons: list[str]


class BillCandidate(BaseModel):
    transaction_id: uuid.UUID
    posting_id: uuid.UUID
    date: dt.date
    account: str
    amount_minor: int
    unallocated_minor: int
    reasons: list[str]
    legacy_inbox_reference: str | None = None
    recurring_conflicts: list[str]
    recurring_forecast_before_pln: int | None = None
    recurring_forecast_after_pln: int | None = None


class BillPage(BaseModel):
    items: list[BillResponse]
    total: int
    limit: int
    offset: int


class BillCandidatePage(BaseModel):
    items: list[BillCandidate]
    total: int
    limit: int
    offset: int


class BillFilters(BaseModel):
    kind: BillKind | None = None
    review: BillReview | None = None
    declaration: PaymentDeclaration | None = None
    lifecycle: BillLifecycle | None = None
    due_from: dt.date | None = None
    due_to: dt.date | None = None
    query: str | None = Field(default=None, max_length=200)

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None
