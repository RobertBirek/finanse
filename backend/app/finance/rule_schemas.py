import uuid
from typing import Literal

from pydantic import BaseModel, Field, StrictBool, StrictInt


class StrictRequest(BaseModel):
    model_config = {"extra": "forbid"}


class SettingsChange(StrictRequest):
    expected_version: StrictInt = Field(ge=0)
    uncategorized_category_id: uuid.UUID | None
    rules_enabled: StrictBool
    confirm_future_only: StrictBool


class RuleDraft(StrictRequest):
    display_description: str = Field(min_length=1)
    target_category_id: uuid.UUID


class RuleVersion(StrictRequest):
    expected_version: StrictInt = Field(gt=0)


class RuleEdit(RuleDraft, RuleVersion):
    pass


class RuleApproval(RuleVersion):
    preview_snapshot: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm_future_only: StrictBool


AssignmentKind = Literal["manual", "approved_rule", "approved_llm"]


class AssignmentOrigin(BaseModel):
    origin: AssignmentKind
    version: int
    rule_id: uuid.UUID | None = None
    rule_version: int | None = None
    display_description: str | None = None
    target_path: str | None = None
    proposal_item_id: uuid.UUID | None = None
