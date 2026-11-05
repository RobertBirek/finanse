"""Client contracts distinguish consent, technical job state and immutable proposals."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, StrictBool, StrictInt, model_validator

from app.finance.receipt_read_contracts import (
    ReceiptReadEvidenceView,
    ReceiptReadProblem,
    ReceiptReadReviewInput,
)
from app.finance.receipt_schemas import ReceiptBody

__all__ = [
    "READ_ACTIVE_STATES",
    "ReceiptReadCancel",
    "ReceiptReadContext",
    "ReceiptReadEvidenceView",
    "ReceiptReadExportPreview",
    "ReceiptReadImport",
    "ReceiptReadImportPreview",
    "ReceiptReadImportPreviewRequest",
    "ReceiptReadJobPage",
    "ReceiptReadJobState",
    "ReceiptReadJobView",
    "ReceiptReadPreviewRequest",
    "ReceiptReadProblem",
    "ReceiptReadProposal",
    "ReceiptReadQuality",
    "ReceiptReadResultView",
    "ReceiptReadReviewInput",
    "ReceiptReadSourceView",
    "ReceiptReadStart",
]

ReceiptReadJobState = Literal[
    "pending",
    "preparing",
    "dispatched",
    "succeeded",
    "failed",
    "unknown",
    "paused",
    "cancelled",
    "superseded",
]
READ_ACTIVE_STATES = frozenset({"pending", "preparing", "dispatched"})
ReceiptReadQuality = Literal["complete", "partial", "unsupported"]


class ReadInput(BaseModel):
    model_config = {"extra": "forbid"}


class ReceiptReadProposal(BaseModel):
    body: ReceiptBody
    problems: list[ReceiptReadProblem]
    importable: bool


class ReceiptReadSourceView(BaseModel):
    document_id: uuid.UUID
    name: str
    mime_type: str
    source_sha256: str
    allowed: bool
    blocked_reason: str | None


class ReceiptReadContext(BaseModel):
    bill_id: uuid.UUID
    bill_version: int
    state_version: int
    enabled: bool
    blocked_reason: str | None
    policy_epoch: int
    provider: str | None
    model: str | None
    limits: dict[str, int]
    sources: list[ReceiptReadSourceView]
    next_source_cursor: str | None


class ReceiptReadPreviewRequest(ReadInput):
    document_id: uuid.UUID
    reread_of_job_id: uuid.UUID | None = None


class ReceiptReadExportPreview(BaseModel):
    document_id: uuid.UUID
    source_sha256: str
    export_snapshot: str
    policy_epoch: int
    provider: str
    model: str
    reread_of_job_id: uuid.UUID | None
    limits: dict[str, int]
    remaining_user_calls: int
    remaining_global_calls: int
    notice: str


class ReceiptReadStart(ReceiptReadPreviewRequest):
    expected_export_snapshot: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: StrictBool

    @model_validator(mode="after")
    def confirmation(self) -> "ReceiptReadStart":
        if not self.confirmed:
            raise ValueError("Wymagana zgoda na eksport całego obrazu")
        return self


class ReceiptReadCancel(ReadInput):
    expected_version: StrictInt = Field(gt=0)


class ReceiptReadJobView(BaseModel):
    id: uuid.UUID
    bill_id: uuid.UUID
    document_id: uuid.UUID
    generation: int
    version: int
    state: ReceiptReadJobState
    source_sha256: str
    dispatched: bool
    extraction_id: uuid.UUID | None
    error_code: str | None
    can_cancel: bool
    poll_after_ms: int | None
    created_at: datetime


class ReceiptReadJobPage(BaseModel):
    items: list[ReceiptReadJobView]
    next_cursor: str | None


class ReceiptReadResultView(BaseModel):
    job: ReceiptReadJobView
    extraction_id: uuid.UUID
    payload_sha256: str
    proposal: ReceiptReadProposal
    payload: dict[str, Any]
    source_sha256: str
    derivative_sha256: str
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    quality: ReceiptReadQuality
    created_at: datetime


class ReceiptReadImportPreviewRequest(ReadInput):
    job_id: uuid.UUID
    expected_state_version: StrictInt = Field(ge=0)


class ReceiptReadImportPreview(BaseModel):
    job_id: uuid.UUID
    extraction_id: uuid.UUID
    payload_sha256: str
    bill_version: int
    state_version: int
    import_snapshot: str
    will_replace_draft: bool
    proposal: ReceiptReadProposal


class ReceiptReadImport(ReceiptReadImportPreviewRequest):
    expected_import_snapshot: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed_replace: StrictBool

    @model_validator(mode="after")
    def confirmation(self) -> "ReceiptReadImport":
        if not self.confirmed_replace:
            raise ValueError("Wymagane jawne przeniesienie do nowego szkicu")
        return self
