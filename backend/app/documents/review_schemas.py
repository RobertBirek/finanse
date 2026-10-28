import uuid
from typing import Literal

from pydantic import BaseModel


class ReviewSuggestion(BaseModel):
    document_type: Literal["invoice", "receipt", "unsupported", "multiple"]
    fields: dict[str, object | None]
    provenance: dict[str, str]
    parser_version: str | None = None


class ReviewResponse(ReviewSuggestion):
    id: uuid.UUID
    document_id: uuid.UUID
    revision: int
    status: Literal["pending", "processing", "ready", "incomplete", "error"]
    error_code: str | None = None
