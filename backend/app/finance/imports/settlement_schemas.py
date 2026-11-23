"""Only identified rows and category choices may be sent for confirmation."""

import datetime as dt
import uuid
from typing import Literal, Self

from pydantic import Field, StrictBool, model_validator

from app.finance.imports.schemas import ImportDTO


class SettlementTarget(ImportDTO):
    id: uuid.UUID
    description: str
    date: dt.date


class SettlementRow(ImportDTO):
    id: uuid.UUID
    description: str
    date: dt.date | None
    amount: int
    currency: str
    status: Literal["settled", "link", "create", "review"]
    reason: str
    kind: Literal["expense", "income"] | None = None
    category_id: uuid.UUID | None = None
    target: SettlementTarget | None = None
    acknowledgement: str | None = None


class SettlementPreview(ImportDTO):
    batch_id: uuid.UUID
    account_id: uuid.UUID
    version: int
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    rows: list[SettlementRow]


class SettlementSelection(ImportDTO):
    row_id: uuid.UUID
    category_id: uuid.UUID | None = None


class SettlementConfirm(ImportDTO):
    account_id: uuid.UUID
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection: list[SettlementSelection] = Field(min_length=1)
    acknowledgements: list[str] = Field(default_factory=list)
    confirmed: StrictBool

    @model_validator(mode="after")
    def validate_confirmation(self) -> Self:
        if not self.confirmed or len({item.row_id for item in self.selection}) != len(
            self.selection
        ):
            raise ValueError("Potwierdź podgląd i wybierz każdy wiersz co najwyżej raz.")
        return self
