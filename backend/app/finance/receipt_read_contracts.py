"""Acyclic evidence contracts shared by receipt bodies and image-read responses."""

import uuid
from typing import Any

from pydantic import BaseModel, Field


class ReceiptReadProblem(BaseModel):
    key: str = Field(max_length=200)
    code: str = Field(max_length=100)
    line_index: int | None = None
    discount_index: int | None = None
    message: str = Field(max_length=500)
    requires_ack: bool


class ReceiptReadReviewInput(BaseModel):
    model_config = {"extra": "forbid"}
    extraction_id: uuid.UUID
    expected_extraction_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    acknowledged_problem_keys: list[str] = Field(max_length=5000)


class ReceiptReadEvidenceView(BaseModel):
    extraction_id: uuid.UUID
    extraction_sha256: str
    job_id: uuid.UUID
    source_document_id: uuid.UUID
    source_sha256: str
    line_map: dict[str, Any]
    discount_map: dict[str, Any]
    pending_problems: list[ReceiptReadProblem]
    acknowledgements: dict[str, str]
