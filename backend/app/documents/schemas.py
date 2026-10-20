import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _DocumentExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    detected: bool

    @field_validator("detected", mode="before")
    @classmethod
    def require_boolean_detection(cls, value: object) -> object:
        # Literal[True/False] alone also accepts integer 1/0 in Pydantic.
        if type(value) is not bool:
            raise ValueError("detected must be a boolean")
        return value


class DocumentNoFinancialData(_DocumentExtraction):
    detected: Literal[False]


class DocumentFinancialData(_DocumentExtraction):
    detected: Literal[True]
    type: Literal["expense", "income"]
    amount: int = Field(gt=0, le=9223372036854775807)
    currency: Literal["PLN", "EUR", "USD"]
    description: str = Field(min_length=1, max_length=2000)
    date: dt.date | None = None
    category_suggestion: str | None = Field(default=None, max_length=200)

    @field_validator("date", mode="before")
    @classmethod
    def require_iso_calendar_date(cls, value: object) -> object:
        if isinstance(value, str):
            parsed = dt.date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError("date must use YYYY-MM-DD")
            return parsed
        return value


class DocumentStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


class DocumentResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    original_name: str
    mime_type: str
    sha256_hash: str
    size_bytes: int
    status: str
    storage_path: str
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


class DocumentTextResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    extracted_text: str
    ocr_engine: str | None = None
    extracted_at: dt.datetime | None = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    document: DocumentResponse
    is_duplicate: bool = False
