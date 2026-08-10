import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class InboxItemCreate(BaseModel):
    content: str = Field(min_length=1)
    source_type: str = Field(default="text", max_length=50)


class InboxItemUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1)
    target_type: str | None = Field(default=None, max_length=50)
    target_id: uuid.UUID | None = None
    is_processed: bool | None = None


class ProcessInboxItem(BaseModel):
    target_type: str = Field(pattern=r"^(task|project|transaction|document|decision|reference)$")


class InboxItemResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    content: str
    source_type: str
    target_type: str | None
    target_id: uuid.UUID | None
    is_processed: bool
    classified_by: str | None
    agent_suggestion: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
