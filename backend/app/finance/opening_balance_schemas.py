"""The client supplies a signed amount, never ledger legs or a source marker."""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field

MAX_MINOR = 9007199254740991


class OpeningBalanceInput(BaseModel):
    model_config = {"extra": "forbid"}
    amount_minor: int = Field(default=0, strict=True, ge=-MAX_MINOR, le=MAX_MINOR)
    date: dt.date | None = None
    fx_rate: Decimal | None = Field(
        default=None,
        gt=0,
        lt=1_000_000,
        max_digits=12,
        decimal_places=6,
        allow_inf_nan=False,
    )


class OpeningBalanceUpdate(OpeningBalanceInput):
    amount_minor: int = Field(strict=True, ge=-MAX_MINOR, le=MAX_MINOR)
    date: dt.date
    expected_version: int = Field(strict=True, ge=1)


class OpeningBalanceView(BaseModel):
    amount_minor: int
    date: dt.date
    fx_rate: Decimal | None
    version: int
    can_edit: bool
    blocked_reason: str | None = None
