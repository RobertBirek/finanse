"""Strict, model-facing payloads for the document vision adapter."""

from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.documents.review_schemas import ReviewDocumentType, ReviewFields, ReviewSuggestion

VisionWarning = Literal["unreadable", "missing_required_fields", "unsupported_document"]


class VisionFields(BaseModel):
    """Every field is explicitly present; unknown values must be null."""

    model_config = ConfigDict(extra="forbid", strict=True)

    supplier_name: str | None = Field(..., max_length=200)
    supplier_tax_id: str | None = Field(..., max_length=64)
    number: str | None = Field(..., max_length=100)
    issue_date: str | None = Field(...)
    sale_date: str | None = Field(...)
    due_date: str | None = Field(...)
    description: str | None = Field(..., max_length=2000)
    payee_iban: str | None = Field(..., max_length=34)
    total: str | None = Field(..., max_length=32)
    currency: Literal["PLN", "EUR", "USD"] | None = Field(...)


class VisionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    document_type: ReviewDocumentType
    fields: VisionFields
    warnings: list[VisionWarning]


class VisionExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, arbitrary_types_allowed=True)

    suggestion: ReviewSuggestion
    warnings: tuple[VisionWarning, ...]
    ready: bool


def to_minor_units(total: str) -> int:
    """Convert a canonical decimal source amount to exact minor units."""
    try:
        value = Decimal(total)
    except (InvalidOperation, ValueError) as error:
        raise ValueError("invalid_amount") from error
    exponent = value.as_tuple().exponent
    if (
        not value.is_finite()
        or value <= 0
        or not isinstance(exponent, int)
        or exponent < -2
        or format(value, "f") != total
    ):
        raise ValueError("invalid_amount")
    minor_units = int(value * 100)
    if minor_units > 9_007_199_254_740_991:
        raise ValueError("invalid_amount")
    return minor_units


def review_suggestion_from_payload(
    payload: VisionPayload, *, parser_version: str
) -> ReviewSuggestion:
    """Attach provenance solely from trusted backend configuration."""
    fields = ReviewFields.model_validate(payload.fields.model_dump())
    return ReviewSuggestion(
        document_type=payload.document_type,
        fields=fields,
        provenance={"source": "vision"},
        parser_version=parser_version,
    )
