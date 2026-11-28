"""Pure domain contracts for conditional recurring obligations."""

import uuid
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.models import ConditionalRecurringObligation as ObligationRecord
from app.finance.queries import lock_accounts
from app.finance.schemas import (
    ConditionalRecurringObligationCreate,
    ConditionalRecurringObligationUpdate,
)

Currency = Literal["PLN", "EUR", "USD"]
Cadence = Literal["monthly", "annual"]
ConditionState = Literal["satisfied", "not_satisfied", "unknown"]
ObligationVariant = Literal["primary", "fallback"]


class NativeAmount(BaseModel):
    """An amount in the source currency, never a converted forecast value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    amount_minor: StrictInt = Field(gt=0)
    source_currency: Currency


class ConditionalRecurringObligation(BaseModel):
    """A conditional expense with explicit native-currency outcomes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    condition_key: str
    cadence: Cadence
    due_month: StrictInt | None = Field(default=None, ge=1, le=12)
    due_day: StrictInt = Field(ge=1, le=28)
    primary: NativeAmount
    fallback: NativeAmount | None

    @field_validator("condition_key")
    @classmethod
    def validate_condition_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("condition_key must not be blank")
        return value

    @model_validator(mode="after")
    def validate_recurrence_anchor(self) -> "ConditionalRecurringObligation":
        if self.cadence == "annual" and self.due_month is None:
            raise ValueError("annual obligations require due_month")
        if self.cadence == "monthly" and self.due_month is not None:
            raise ValueError("monthly obligations must not set due_month")
        return self


class ConditionalForecastStatus(BaseModel):
    """An intentionally non-numeric forecast result for this foundation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["unavailable"] = "unavailable"
    reason: Literal[
        "condition_unresolved",
        "fallback_amount_unknown",
        "native_currency_forecast_unsupported",
    ]
    selected_variant: ObligationVariant | None
    native_amount: NativeAmount | None


def forecast_status(
    obligation: ConditionalRecurringObligation, *, condition_state: ConditionState
) -> ConditionalForecastStatus:
    """Expose the selected native amount without projecting or converting it."""
    if condition_state not in {"satisfied", "not_satisfied", "unknown"}:
        raise ValueError("condition_state is invalid")
    if condition_state == "unknown":
        return ConditionalForecastStatus(
            reason="condition_unresolved",
            selected_variant=None,
            native_amount=None,
        )
    selected_variant: ObligationVariant = (
        "primary" if condition_state == "satisfied" else "fallback"
    )
    native_amount = getattr(obligation, selected_variant)
    if native_amount is None:
        return ConditionalForecastStatus(
            reason="fallback_amount_unknown",
            selected_variant=selected_variant,
            native_amount=None,
        )
    return ConditionalForecastStatus(
        reason="native_currency_forecast_unsupported",
        selected_variant=selected_variant,
        native_amount=native_amount,
    )


def occurrences(obligation: ObligationRecord, *, start: date, end: date) -> list[date]:
    """Return calendar dates only; no amount conversion or ledger side effect."""
    if obligation.cadence == "annual":
        if obligation.due_month is None:
            raise ValueError("Annual obligation is missing due_month")
        return [
            date(year, obligation.due_month, obligation.due_day)
            for year in range(start.year, end.year + 1)
            if start <= date(year, obligation.due_month, obligation.due_day) <= end
        ]
    result: list[date] = []
    month = start.replace(day=1)
    while month <= end:
        due = month.replace(day=obligation.due_day)
        if start <= due <= end:
            result.append(due)
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return result


async def _validate_accounts(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    primary_account_id: uuid.UUID,
    primary_currency: str,
    fallback_account_id: uuid.UUID,
    fallback_currency: str,
) -> None:
    if primary_account_id == fallback_account_id:
        raise ValueError("Primary and fallback accounts must be different")
    accounts = await lock_accounts(db, user_id, {primary_account_id, fallback_account_id})
    for role, account_id, currency in (
        ("Primary", primary_account_id, primary_currency),
        ("Fallback", fallback_account_id, fallback_currency),
    ):
        account = accounts.get(account_id)
        if account is None:
            raise ValueError(f"{role} obligation account not found")
        if not account.is_active or not account.is_budget_account:
            raise ValueError(f"{role} obligation requires an active budget account")
        if account.currency.upper() != currency:
            raise ValueError(f"{role} obligation currency does not match account currency")


def _validate_anchor(cadence: str, due_month: int | None) -> None:
    if cadence == "annual" and due_month is None:
        raise ValueError("due_month is required for annual cadence")
    if cadence == "monthly" and due_month is not None:
        raise ValueError("due_month must be omitted for monthly cadence")


async def create(
    db: AsyncSession, user_id: uuid.UUID, data: ConditionalRecurringObligationCreate
) -> ObligationRecord:
    await _validate_accounts(
        db,
        user_id,
        primary_account_id=data.primary_account_id,
        primary_currency=data.primary_currency,
        fallback_account_id=data.fallback_account_id,
        fallback_currency=data.fallback_currency,
    )
    record = ObligationRecord(user_id=user_id, **data.model_dump())
    db.add(record)
    await db.flush()
    return record


async def list_for_owner(db: AsyncSession, user_id: uuid.UUID) -> list[ObligationRecord]:
    return list(
        (
            await db.execute(
                select(ObligationRecord)
                .where(ObligationRecord.user_id == user_id)
                .order_by(
                    ObligationRecord.is_active.desc(),
                    ObligationRecord.cadence,
                    ObligationRecord.due_month,
                    ObligationRecord.due_day,
                    ObligationRecord.name,
                )
            )
        ).scalars()
    )


async def update(
    db: AsyncSession,
    user_id: uuid.UUID,
    obligation_id: uuid.UUID,
    data: ConditionalRecurringObligationUpdate,
) -> ObligationRecord | None:
    record = await db.scalar(
        select(ObligationRecord).where(
            ObligationRecord.id == obligation_id, ObligationRecord.user_id == user_id
        )
    )
    if record is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    cadence = update_data.get("cadence", record.cadence)
    due_month = update_data.get("due_month", record.due_month)
    _validate_anchor(cadence, due_month)
    await _validate_accounts(
        db,
        user_id,
        primary_account_id=update_data.get("primary_account_id", record.primary_account_id),
        primary_currency=update_data.get("primary_currency", record.primary_currency),
        fallback_account_id=update_data.get("fallback_account_id", record.fallback_account_id),
        fallback_currency=update_data.get("fallback_currency", record.fallback_currency),
    )
    for key, value in update_data.items():
        setattr(record, key, value)
    await db.flush()
    return record


async def delete(db: AsyncSession, user_id: uuid.UUID, obligation_id: uuid.UUID) -> bool:
    record = await db.scalar(
        select(ObligationRecord).where(
            ObligationRecord.id == obligation_id, ObligationRecord.user_id == user_id
        )
    )
    if record is None:
        return False
    await db.delete(record)
    await db.flush()
    return True
