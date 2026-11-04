import uuid
from typing import Literal

from pydantic import BaseModel, Field, StrictInt, model_validator

from app.config import settings
from app.finance.bills_schemas import MAX_SAFE_MINOR
from app.finance.rule_schemas import AssignmentOrigin


class CategorizationPart(BaseModel):
    model_config = {"extra": "forbid"}
    category_id: uuid.UUID
    amount_minor: StrictInt = Field(gt=0, le=MAX_SAFE_MINOR)


class PartsRequest(BaseModel):
    model_config = {"extra": "forbid"}
    expected_version: StrictInt = Field(ge=0)
    parts: list[CategorizationPart] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_parts(self) -> "PartsRequest":
        if len(self.parts) > settings.FINANCE_CATEGORY_SPLIT_MAX_PARTS:
            raise ValueError("Zbyt wiele części podziału")
        if len({p.category_id for p in self.parts}) != len(self.parts):
            raise ValueError("Każda kategoria może wystąpić tylko raz")
        return self


class CategorizationPreviewRequest(PartsRequest):
    expected_context_snapshot: str = Field(pattern=r"^[0-9a-f]{64}$")


class CategorizationApply(PartsRequest):
    expected_preview_snapshot: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: Literal[True]

    @model_validator(mode="before")
    @classmethod
    def explicit_confirmation(cls, value: object) -> object:
        if isinstance(value, dict) and value.get("confirmed") is not True:
            raise ValueError("Wymagane jawne zatwierdzenie")
        return value


class CategorizationEligibility(BaseModel):
    allowed: bool
    reason_code: str | None = None
    message: str | None = None


class CategorizationContext(BaseModel):
    transaction_id: uuid.UUID
    eligibility: CategorizationEligibility
    amount_minor: int | None
    currency: str | None
    parts: list[CategorizationPart]
    version: int
    source: Literal["manual"] | None
    context_snapshot: str
    max_parts: int
    assignment_origin: AssignmentOrigin | None = None


class CategorizationPreview(BaseModel):
    expected_version: int
    preview_snapshot: str
    before_parts: list[CategorizationPart]
    after_parts: list[CategorizationPart]
    target_paths: dict[str, str]
