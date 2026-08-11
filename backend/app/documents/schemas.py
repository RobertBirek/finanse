import uuid
import datetime as dt
from typing import Optional

from pydantic import BaseModel


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
    ocr_engine: Optional[str] = None
    extracted_at: Optional[dt.datetime] = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    document: DocumentResponse
    is_duplicate: bool = False
