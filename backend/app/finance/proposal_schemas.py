import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, StrictBool, StrictInt, model_validator

from app.finance.categorization_schemas import CategorizationContext, CategorizationPart


class ProposalVersion(BaseModel):
    model_config = {"extra": "forbid"}
    expected_version: StrictInt = Field(gt=0)


class ProposalApply(ProposalVersion):
    preview_snapshot: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: StrictBool

    @model_validator(mode="after")
    def require_confirmation(self) -> "ProposalApply":
        if not self.confirmed:
            raise ValueError("Explicit confirmation required")
        return self


class ProposalDetail(BaseModel):
    id: uuid.UUID
    version: int
    status: str
    transaction_id: uuid.UUID | None
    description: str
    amount_minor: int | None
    currency: Literal["PLN"] = "PLN"
    decision: str
    explanation: str
    confidence: str
    new_category: dict[str, str | None] | None
    current_parts: list[CategorizationPart]
    target_path: str | None
    eligible: bool
    blocked_reason: str | None
    expires_at: datetime


class ProposalPage(BaseModel):
    items: list[ProposalDetail]
    next_cursor: str | None
    page_size: int


class ProposalPreview(BaseModel):
    proposal_id: uuid.UUID
    expected_version: int
    source_version: int
    context_snapshot: str
    preview_snapshot: str
    amount_minor: int
    currency: Literal["PLN"] = "PLN"
    before_parts: list[CategorizationPart]
    after_parts: list[CategorizationPart]
    target_path: str
    explanation: str
    confidence: str
    expires_at: datetime


class ProposalDecision(BaseModel):
    proposal_id: uuid.UUID
    version: int
    status: Literal["approved", "rejected"]
    context: CategorizationContext | None = None
    grant: dict[str, Any] | None = None
