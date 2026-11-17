"""Registration evidence is independent of the latest OCR/AI result."""

import uuid
from typing import Literal

from pydantic import BaseModel

DraftIntentState = Literal["pending", "needs_review", "failed", "succeeded"]


class FinanceDraftSummary(BaseModel):
    state: Literal["not_requested", "pending", "needs_review", "failed", "succeeded"] = (
        "not_requested"
    )
    error_code: str | None = None
    bill_id: uuid.UUID | None = None
    revision_id: uuid.UUID | None = None
    review: Literal["draft", "approved", "rejected"] | None = None
    lifecycle: Literal["active", "archived", "cancelled"] | None = None
