"""Public consent/usage contracts; server activation has no HTTP input schema."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, StrictBool, StrictInt, model_validator


class SuggestionSettingsChange(BaseModel):
    model_config = {"extra": "forbid"}
    expected_version: StrictInt = Field(ge=0)
    enabled: StrictBool
    expected_server_epoch: StrictInt | None = Field(default=None, ge=0)
    expected_configuration_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    confirm_future_only: StrictBool = False
    confirm_data_export: StrictBool = False


class SuggestionSettingsResponse(BaseModel):
    version: int
    enabled: bool
    effective_enabled: bool
    available: bool
    blocked_reason: str | None
    server_epoch: int
    configuration_fingerprint: str | None
    daily_call_limit: int
    max_description_chars: int
    max_categories: int
    review_page_size: int
    privacy_text: str


class SuggestionUsageResponse(BaseModel):
    usage_date: date
    limit: int
    held: int
    dispatched: int
    known: int
    unknown: int
    released: int
    remaining_slots: int
    known_input_tokens: int | None
    known_output_tokens: int | None
    cost_status: Literal["unpriced"] = "unpriced"


class SuggestedNewCategory(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    name: str = Field(min_length=1, max_length=200)
    parent_key: str | None
    explanation: str = Field(min_length=1, max_length=2000)


class SuggestionPayload(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    decision: Literal["existing_category", "new_category", "no_suggestion"]
    category_key: str | None
    confidence: Literal["low", "medium", "high"]
    explanation: str = Field(min_length=1, max_length=2000)
    new_category: SuggestedNewCategory | None

    @model_validator(mode="after")
    def exclusive_variant(self) -> "SuggestionPayload":
        if self.decision == "existing_category":
            valid = self.category_key is not None and self.new_category is None
        elif self.decision == "new_category":
            valid = self.category_key is None and self.new_category is not None
        else:
            valid = self.category_key is None and self.new_category is None
        if not valid:
            raise ValueError("Invalid suggestion variant")
        return self
