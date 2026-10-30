import uuid
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ReviewDocumentType = Literal[
    "invoice", "receipt", "statement", "loan_schedule", "other", "unsupported", "multiple"
]


class ReviewFields(BaseModel):
    """Untrusted extracted values; unknown fields are deliberately null."""

    model_config = ConfigDict(extra="forbid", strict=True)

    supplier_name: str | None = Field(default=None, max_length=200)
    supplier_tax_id: str | None = Field(default=None, max_length=64)
    number: str | None = Field(default=None, max_length=100)
    issue_date: str | None = None
    sale_date: str | None = None
    due_date: str | None = None
    description: str | None = Field(default=None, max_length=2000)
    payee_iban: str | None = Field(default=None, max_length=34)
    total: str | None = Field(default=None, max_length=32)
    currency: Literal["PLN", "EUR", "USD"] | None = None

    @field_validator("issue_date", "sale_date", "due_date")
    @classmethod
    def require_iso_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from datetime import date

        try:
            parsed = date.fromisoformat(value)
        except ValueError as error:
            raise ValueError("date must use YYYY-MM-DD") from error
        if parsed.isoformat() != value:
            raise ValueError("date must use YYYY-MM-DD")
        return value

    @field_validator("total")
    @classmethod
    def require_decimal_source_amount(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError) as error:
            raise ValueError("total must be a decimal string") from error
        exponent = parsed.as_tuple().exponent
        if not parsed.is_finite() or parsed <= 0 or not isinstance(exponent, int) or exponent < -2:
            raise ValueError("total must be a positive amount with at most two decimals")
        if format(parsed, "f") != value:
            raise ValueError("total must be a canonical decimal string")
        return value


class ReviewSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    document_type: ReviewDocumentType
    fields: ReviewFields
    provenance: dict[str, str]
    parser_version: str | None = None


class ReviewResponse(ReviewSuggestion):
    id: uuid.UUID
    document_id: uuid.UUID
    revision: int
    status: Literal["pending", "processing", "ready", "incomplete", "error"]
    error_code: str | None = None
