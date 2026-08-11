import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: uuid.UUID | None = None


class SendMessageRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    content: str = Field(min_length=1)


class ToolExecutionResponse(BaseModel):
    id: uuid.UUID
    tool_name: str
    arguments: dict | None = None
    result: dict | None = None
    status: str
    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str | None = None
    tool_calls: list[dict] | None = None
    tool_executions: list[ToolExecutionResponse] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
