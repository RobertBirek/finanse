"""Human receipt-item contracts. No provider fields, derived amounts or implicit grants."""

import unicodedata
import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, StrictBool, StrictInt, field_validator, model_validator

from app.config import settings
from app.finance.bills_schemas import MAX_SAFE_MINOR
from app.finance.categorization_schemas import CategorizationContext, CategorizationPart


def normalize_receipt_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


class ReceiptInput(BaseModel):
    model_config = {"extra": "forbid"}


class ReceiptHistoryRef(ReceiptInput):
    source_bill_id: uuid.UUID
    source_revision_id: uuid.UUID
    source_line_key: uuid.UUID
    category_id: uuid.UUID
    match_kind: Literal["exact", "prefix"]
    algorithm_version: str = Field(min_length=1, max_length=64)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReceiptLineInput(ReceiptInput):
    line_key: uuid.UUID
    name: str = Field(max_length=2000)
    amount_minor: StrictInt | None = Field(default=None, ge=0, le=MAX_SAFE_MINOR)
    category_id: uuid.UUID | None = None
    hint: ReceiptHistoryRef | None = None

    @field_validator("name")
    @classmethod
    def bounded_name(cls, value: str) -> str:
        if max(len(value), len(normalize_receipt_name(value))) > 2000:
            raise ValueError("Nazwa przekracza limit znaków")
        return value


class ReceiptDiscountShareInput(ReceiptInput):
    line_key: uuid.UUID
    amount_minor: StrictInt | None = Field(default=None, gt=0, le=MAX_SAFE_MINOR)


class ReceiptDiscountInput(ReceiptInput):
    discount_key: uuid.UUID
    name: str = Field(max_length=2000)
    amount_minor: StrictInt | None = Field(default=None, gt=0, le=MAX_SAFE_MINOR)
    shares: list[ReceiptDiscountShareInput] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def bounded_name(cls, value: str) -> str:
        return ReceiptLineInput.bounded_name(value)


class ReceiptBody(ReceiptInput):
    store_id: uuid.UUID | None = None
    store_version: StrictInt | None = Field(default=None, gt=0)
    lines: list[ReceiptLineInput] = Field(default_factory=list)
    discounts: list[ReceiptDiscountInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_structure(self) -> "ReceiptBody":
        if self.store_id is None and self.store_version is not None:
            raise ValueError("Brak sklepu dla wersji")
        if (
            len(self.lines) > 1000
            or len(self.discounts) > 200
            or sum(len(d.shares) for d in self.discounts) > 5000
        ):
            raise ValueError("Zbyt wiele pozycji, rabatów lub udziałów")
        keys = {r.line_key for r in self.lines}
        if len(keys) != len(self.lines) or len({d.discount_key for d in self.discounts}) != len(
            self.discounts
        ):
            raise ValueError("Powtórzone identyfikatory pozycji lub rabatu")
        for discount in self.discounts:
            refs = [s.line_key for s in discount.shares]
            if len(set(refs)) != len(refs) or not set(refs) <= keys:
                raise ValueError("Udział rabatu wskazuje powtórzoną lub brakującą pozycję")
        return self


class ReceiptProblem(BaseModel):
    code: str
    line_key: uuid.UUID | None = None
    discount_key: uuid.UUID | None = None
    message: str


def validate_receipt_input_limits(body: ReceiptBody) -> None:
    """Current intake limits never make retained evidence/command replay unreadable."""
    if (
        len(body.lines) > settings.FINANCE_RECEIPT_MAX_LINES
        or len(body.discounts) > settings.FINANCE_RECEIPT_MAX_DISCOUNTS
        or sum(len(d.shares) for d in body.discounts) > settings.FINANCE_RECEIPT_MAX_DISCOUNT_SHARES
    ):
        raise ValueError("Zbyt wiele pozycji, rabatów lub udziałów")
    if any(
        max(len(name), len(normalize_receipt_name(name)))
        > settings.FINANCE_RECEIPT_ITEM_NAME_MAX_CHARS
        for name in [*(r.name for r in body.lines), *(d.name for d in body.discounts)]
    ):
        raise ValueError("Nazwa przekracza limit znaków")


def validate_receipt_store_limit(name: str) -> None:
    if (
        max(len(name), len(normalize_receipt_name(name)))
        > settings.FINANCE_RECEIPT_STORE_NAME_MAX_CHARS
    ):
        raise ValueError("Nazwa sklepu przekracza limit znaków")


class ReceiptLineNet(BaseModel):
    line_key: uuid.UUID
    net_minor: int | None


class ReceiptCalculation(BaseModel):
    line_nets: list[ReceiptLineNet]
    net_total_minor: int | None
    difference_minor: int | None
    parts: list[CategorizationPart]
    problems: list[ReceiptProblem]


class ReceiptStoreCreate(ReceiptInput):
    name: str = Field(min_length=1, max_length=500)

    @field_validator("name")
    @classmethod
    def bounded_store(cls, value: str) -> str:
        if not value.strip() or max(len(value), len(normalize_receipt_name(value))) > 500:
            raise ValueError("Podaj nazwę sklepu w dozwolonym limicie")
        return value


class ReceiptVersion(ReceiptInput):
    expected_version: StrictInt = Field(ge=0)


class ReceiptStoreChange(ReceiptVersion):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    active: StrictBool | None = None

    @model_validator(mode="after")
    def valid_changes(self) -> "ReceiptStoreChange":
        if not self.model_fields_set - {"expected_version"} or any(
            getattr(self, key) is None for key in self.model_fields_set - {"expected_version"}
        ):
            raise ValueError("Podaj niepustą zmianę sklepu")
        if self.name is not None:
            ReceiptStoreCreate.bounded_store(self.name)
        return self


class ReceiptStoreResponse(BaseModel):
    id: uuid.UUID
    name: str
    active: bool
    version: int


class ReceiptStorePage(BaseModel):
    items: list[ReceiptStoreResponse]
    next_cursor: str | None


class ReceiptDraftSave(ReceiptVersion):
    expected_bill_version: StrictInt = Field(gt=0)
    body: ReceiptBody


class ReceiptItemsApprove(ReceiptVersion):
    draft_revision_id: uuid.UUID
    expected_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: StrictBool

    @model_validator(mode="after")
    def confirmation(self) -> "ReceiptItemsApprove":
        if not self.confirmed:
            raise ValueError("Wymagane świadome zatwierdzenie")
        return self


class ReceiptLimits(BaseModel):
    max_lines: int
    max_discounts: int
    max_discount_shares: int
    item_name_max_chars: int
    store_name_max_chars: int
    history_page_size: int
    history_prefix_min_chars: int


class ReceiptRevisionView(BaseModel):
    id: uuid.UUID
    sequence: int
    kind: Literal["draft", "approved"]
    header_sha256: str
    body_sha256: str
    body: ReceiptBody
    created_at: datetime
    current: bool
    problems: list[ReceiptProblem]


class ReceiptItemsContext(BaseModel):
    bill_id: uuid.UUID
    bill_version: int
    state_version: int
    editable: bool
    blocked_reason: str | None
    draft: ReceiptRevisionView | None
    approved: ReceiptRevisionView | None
    calculation: ReceiptCalculation | None
    eligible_category_ids: list[uuid.UUID]
    limits: ReceiptLimits


class ReceiptHistoryHint(BaseModel):
    ref: ReceiptHistoryRef
    product_name: str
    category_path: str
    purchased_on: date | None
    approved_at: datetime


class ReceiptHistoryPage(BaseModel):
    items: list[ReceiptHistoryHint]
    match_kind: Literal["exact", "prefix", "none"]
    conflict: bool
    has_more: bool
    history_incomplete: bool


class ReceiptPaymentRequest(ReceiptInput):
    expected_state_version: StrictInt = Field(gt=0)
    approved_revision_id: uuid.UUID


class ReceiptPaymentApply(ReceiptPaymentRequest):
    expected_preview_snapshot: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: StrictBool

    @model_validator(mode="after")
    def confirmation(self) -> "ReceiptPaymentApply":
        if not self.confirmed:
            raise ValueError("Wymagane świadome zatwierdzenie")
        return self


class ReceiptPaymentPreview(ReceiptPaymentRequest):
    transaction_id: uuid.UUID
    context_snapshot: str
    preview_snapshot: str
    before_parts: list[CategorizationPart]
    after_parts: list[CategorizationPart]
    target_paths: dict[str, str]
    line_nets: list[ReceiptLineNet]
    body_sha256: str
    total_minor: int
    currency: Literal["PLN"] = "PLN"
    notice: str = (
        "Zmieni się tylko podział kategorii. Kwota, konto i daty płatności pozostaną bez zmian."
    )


class ReceiptApplicationStatus(BaseModel):
    receipt_id: uuid.UUID
    revision_id: uuid.UUID
    transaction_id: uuid.UUID
    items_changed: bool
    ledger_changed: bool


class ReceiptPaymentContext(BaseModel):
    allowed: bool
    blocked_reason: str | None
    last_application: ReceiptApplicationStatus | None


class ReceiptPaymentResult(BaseModel):
    context: CategorizationContext
    state_version: int
    receipt_id: uuid.UUID
    revision_id: uuid.UUID
    grant: dict[str, Any]
