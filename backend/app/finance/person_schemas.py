"""Person metadata input cannot carry ledger amounts or a foreign owner."""

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.finance.schemas import TransactionResponse


class PersonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    reference_account_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def safe_name(cls, value: str) -> str:
        if "\0" in value:
            raise ValueError("Nazwa zawiera niedozwolony znak.")
        return value


class PersonUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(strict=True, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = Field(default=None, strict=True)
    reference_account_id: uuid.UUID | None = None

    @field_validator("name", "is_active")
    @classmethod
    def not_null(cls, value: str | bool | None) -> str | bool:
        if value is None or (isinstance(value, str) and "\0" in value):
            raise ValueError("Pole nie może być puste ani zawierać niedozwolonych znaków.")
        return value


class PersonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    is_active: bool
    version: int
    reference_account_id: uuid.UUID | None


class PersonPage(BaseModel):
    items: list[PersonResponse]
    total: int
    limit: int
    offset: int


class PersonLinkContext(BaseModel):
    transaction_id: uuid.UUID
    snapshot: str
    person: PersonResponse | None
    eligible: bool
    reason: str | None


class GiftUnlinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_transaction_snapshot: str = Field(pattern=r"^[a-f0-9]{64}$")


class GiftLinkRequest(GiftUnlinkRequest):
    person_id: uuid.UUID


class PersonSummary(BaseModel):
    person_id: uuid.UUID
    gift_count: int
    received_gifts_pln: int
    received_by_currency: dict[str, int]


class PersonGiftPage(BaseModel):
    items: list[TransactionResponse]
    total: int
    limit: int
    offset: int
