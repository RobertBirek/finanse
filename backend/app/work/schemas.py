import uuid
from datetime import date, datetime
from typing import ClassVar, Self

from pydantic import AwareDatetime, BaseModel, Field, model_validator


class _WorkUpdate(BaseModel):
    _required_on_update: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def reject_explicit_null(self) -> Self:
        invalid = [
            name
            for name in self._required_on_update
            if name in self.model_fields_set and getattr(self, name) is None
        ]
        if invalid:
            raise ValueError(f"Fields cannot be null: {', '.join(invalid)}")
        return self


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: str = Field(default="active", pattern=r"^(active|on_hold|completed|cancelled)$")
    deadline: date | None = None
    color: str | None = None


class ProjectUpdate(_WorkUpdate):
    _required_on_update = ("name", "status")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = Field(default=None, pattern=r"^(active|on_hold|completed|cancelled)$")
    deadline: date | None = None
    color: str | None = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: str | None
    status: str
    deadline: date | None
    color: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    project_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    status: str = Field(default="todo", pattern=r"^(todo|in_progress|done|cancelled)$")
    priority: str = Field(default="medium", pattern=r"^(low|medium|high|urgent)$")
    due_date: date | None = None
    estimated_minutes: int | None = None
    source: str = Field(default="manual", max_length=50)


class TaskUpdate(_WorkUpdate):
    _required_on_update = ("title", "status", "priority")
    project_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    status: str | None = Field(default=None, pattern=r"^(todo|in_progress|done|cancelled)$")
    priority: str | None = Field(default=None, pattern=r"^(low|medium|high|urgent)$")
    due_date: date | None = None
    estimated_minutes: int | None = None
    actual_minutes: int | None = None


class TaskResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    description: str | None
    status: str
    priority: str
    due_date: date | None
    estimated_minutes: int | None
    actual_minutes: int | None
    completed_at: datetime | None
    source: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TimeBlockCreate(BaseModel):
    task_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    start_time: AwareDatetime
    end_time: AwareDatetime
    block_type: str = Field(default="deep_work", pattern=r"^(deep_work|shallow|meeting|break)$")
    title: str = Field(min_length=1, max_length=500)


class TimeBlockUpdate(_WorkUpdate):
    _required_on_update = ("title", "block_type", "start_time", "end_time")
    task_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None
    block_type: str | None = Field(default=None, pattern=r"^(deep_work|shallow|meeting|break)$")
    title: str | None = Field(default=None, min_length=1, max_length=500)


class TimeBlockResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    task_id: uuid.UUID | None
    project_id: uuid.UUID | None
    start_time: datetime
    end_time: datetime
    block_type: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
