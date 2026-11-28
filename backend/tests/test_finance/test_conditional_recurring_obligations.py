"""Pure-domain contract for conditional recurring obligations."""

import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.finance.conditional_recurring_obligations import (
    ConditionalRecurringObligation,
    NativeAmount,
)


def test_create_contract_requires_explicit_due_day_and_preserves_native_account_variants() -> None:
    from app.finance.schemas import ConditionalRecurringObligationCreate

    primary_account_id = "11111111-1111-1111-1111-111111111111"
    fallback_account_id = "22222222-2222-2222-2222-222222222222"
    obligation = ConditionalRecurringObligationCreate(
        name="Subscription",
        condition_key="subscription_eligible",
        cadence="monthly",
        due_day=15,
        primary_account_id=primary_account_id,
        primary_amount_minor=2000,
        primary_currency="USD",
        fallback_account_id=fallback_account_id,
        fallback_amount_minor=8000,
        fallback_currency="PLN",
    )

    assert obligation.primary_account_id.hex == primary_account_id.replace("-", "")
    assert obligation.primary_currency == "USD"
    assert obligation.fallback_account_id.hex == fallback_account_id.replace("-", "")
    assert obligation.fallback_currency == "PLN"


@pytest.mark.asyncio
async def test_account_validation_uses_shared_locks_for_both_owned_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fails if validation can read currencies while an exclusive account edit is in flight."""

    import app.finance.conditional_recurring_obligations as obligations

    owner_id, primary_id, fallback_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    captured: list[tuple[uuid.UUID, set[uuid.UUID]]] = []

    async def lock_accounts(_db: object, user_id: uuid.UUID, account_ids: set[uuid.UUID]) -> dict:
        captured.append((user_id, account_ids))
        return {
            primary_id: SimpleNamespace(
                id=primary_id, is_active=True, is_budget_account=True, currency="EUR"
            ),
            fallback_id: SimpleNamespace(
                id=fallback_id, is_active=True, is_budget_account=True, currency="PLN"
            ),
        }

    monkeypatch.setattr(obligations, "lock_accounts", lock_accounts)

    await obligations._validate_accounts(
        object(),
        owner_id,
        primary_account_id=primary_id,
        primary_currency="EUR",
        fallback_account_id=fallback_id,
        fallback_currency="PLN",
    )

    assert captured == [(owner_id, {primary_id, fallback_id})]


def test_create_contract_rejects_missing_or_inferred_due_day() -> None:
    from app.finance.schemas import ConditionalRecurringObligationCreate

    with pytest.raises(ValidationError):
        ConditionalRecurringObligationCreate(
            name="Subscription",
            condition_key="subscription_eligible",
            cadence="monthly",
            primary_account_id="11111111-1111-1111-1111-111111111111",
            primary_amount_minor=2000,
            primary_currency="USD",
            fallback_account_id="22222222-2222-2222-2222-222222222222",
            fallback_amount_minor=8000,
            fallback_currency="PLN",
        )


def test_create_contract_allows_an_explicitly_unknown_fallback_amount() -> None:
    from app.finance.schemas import ConditionalRecurringObligationCreate

    obligation = ConditionalRecurringObligationCreate(
        name="Subscription",
        condition_key="subscription_eligible",
        cadence="monthly",
        due_day=15,
        primary_account_id="11111111-1111-1111-1111-111111111111",
        primary_amount_minor=2000,
        primary_currency="USD",
        fallback_account_id="22222222-2222-2222-2222-222222222222",
        fallback_amount_minor=None,
        fallback_currency="PLN",
    )

    assert obligation.fallback_amount_minor is None


def test_patch_contract_distinguishes_explicit_unknown_fallback_amount_from_omission() -> None:
    from app.finance.schemas import ConditionalRecurringObligationUpdate

    assert ConditionalRecurringObligationUpdate().model_dump(exclude_unset=True) == {}
    assert ConditionalRecurringObligationUpdate(fallback_amount_minor=None).model_dump(
        exclude_unset=True
    ) == {"fallback_amount_minor": None}


def test_monthly_obligation_occurrences_keep_the_explicit_due_day() -> None:
    from app.finance.conditional_recurring_obligations import occurrences

    obligation = SimpleNamespace(cadence="monthly", due_month=None, due_day=15)

    assert occurrences(obligation, start=date(2026, 1, 16), end=date(2026, 3, 20)) == [
        date(2026, 2, 15),
        date(2026, 3, 15),
    ]


def test_native_amount_keeps_minor_amount_and_source_currency_explicit() -> None:
    amount = NativeAmount(amount_minor=4900, source_currency="EUR")

    assert amount.amount_minor == 4900
    assert amount.source_currency == "EUR"


@pytest.mark.parametrize("amount_minor", [0, -1])
def test_native_amount_rejects_non_positive_values(amount_minor: int) -> None:
    with pytest.raises(ValidationError):
        NativeAmount(amount_minor=amount_minor, source_currency="PLN")


def test_obligation_has_explicit_primary_and_fallback_native_amounts() -> None:
    obligation = ConditionalRecurringObligation(
        condition_key="workday",
        cadence="monthly",
        due_day=5,
        primary=NativeAmount(amount_minor=4900, source_currency="EUR"),
        fallback=NativeAmount(amount_minor=3900, source_currency="EUR"),
    )

    assert obligation.primary.amount_minor == 4900
    assert obligation.primary.source_currency == "EUR"
    assert obligation.fallback.amount_minor == 3900
    assert obligation.fallback.source_currency == "EUR"


def test_annual_obligation_requires_an_explicit_due_month() -> None:
    with pytest.raises(ValidationError):
        ConditionalRecurringObligation(
            condition_key="membership_active",
            cadence="annual",
            due_day=12,
            primary=NativeAmount(amount_minor=12000, source_currency="USD"),
            fallback=NativeAmount(amount_minor=6000, source_currency="USD"),
        )

    annual = ConditionalRecurringObligation(
        condition_key="membership_active",
        cadence="annual",
        due_month=9,
        due_day=12,
        primary=NativeAmount(amount_minor=12000, source_currency="USD"),
        fallback=NativeAmount(amount_minor=6000, source_currency="USD"),
    )

    assert annual.due_month == 9


@pytest.mark.parametrize("due_day", [0, 29])
def test_obligation_rejects_unsafe_calendar_days(due_day: int) -> None:
    with pytest.raises(ValidationError):
        ConditionalRecurringObligation(
            condition_key="workday",
            cadence="monthly",
            due_day=due_day,
            primary=NativeAmount(amount_minor=4900, source_currency="EUR"),
            fallback=NativeAmount(amount_minor=3900, source_currency="EUR"),
        )


def test_forecast_is_unavailable_but_retains_the_selected_primary_native_amount() -> None:
    from app.finance.conditional_recurring_obligations import forecast_status

    obligation = ConditionalRecurringObligation(
        condition_key="workday",
        cadence="monthly",
        due_day=5,
        primary=NativeAmount(amount_minor=4900, source_currency="EUR"),
        fallback=NativeAmount(amount_minor=3900, source_currency="EUR"),
    )

    result = forecast_status(obligation, condition_state="satisfied")

    assert result.status == "unavailable"
    assert result.reason == "native_currency_forecast_unsupported"
    assert result.selected_variant == "primary"
    assert result.native_amount == NativeAmount(amount_minor=4900, source_currency="EUR")


def test_forecast_retains_the_explicit_fallback_currency_without_converting() -> None:
    from app.finance.conditional_recurring_obligations import forecast_status

    result = forecast_status(
        ConditionalRecurringObligation(
            condition_key="membership_active",
            cadence="annual",
            due_month=9,
            due_day=12,
            primary=NativeAmount(amount_minor=12000, source_currency="USD"),
            fallback=NativeAmount(amount_minor=6000, source_currency="EUR"),
        ),
        condition_state="not_satisfied",
    )

    assert result.status == "unavailable"
    assert result.reason == "native_currency_forecast_unsupported"
    assert result.selected_variant == "fallback"
    assert result.native_amount == NativeAmount(amount_minor=6000, source_currency="EUR")


def test_resolved_fallback_without_an_amount_remains_unavailable() -> None:
    from app.finance.conditional_recurring_obligations import forecast_status

    result = forecast_status(
        ConditionalRecurringObligation(
            condition_key="subscription_eligible",
            cadence="monthly",
            due_day=15,
            primary=NativeAmount(amount_minor=2000, source_currency="USD"),
            fallback=None,
        ),
        condition_state="not_satisfied",
    )

    assert result.reason == "fallback_amount_unknown"
    assert result.selected_variant == "fallback"
    assert result.native_amount is None


def test_unresolved_condition_has_no_selected_amount_and_is_unavailable() -> None:
    from app.finance.conditional_recurring_obligations import forecast_status

    result = forecast_status(
        ConditionalRecurringObligation(
            condition_key="workday",
            cadence="monthly",
            due_day=5,
            primary=NativeAmount(amount_minor=4900, source_currency="EUR"),
            fallback=NativeAmount(amount_minor=3900, source_currency="EUR"),
        ),
        condition_state="unknown",
    )

    assert result.status == "unavailable"
    assert result.reason == "condition_unresolved"
    assert result.selected_variant is None
    assert result.native_amount is None


def test_forecast_rejects_an_unknown_condition_state() -> None:
    from app.finance.conditional_recurring_obligations import forecast_status

    obligation = ConditionalRecurringObligation(
        condition_key="workday",
        cadence="monthly",
        due_day=5,
        primary=NativeAmount(amount_minor=4900, source_currency="EUR"),
        fallback=NativeAmount(amount_minor=3900, source_currency="EUR"),
    )

    with pytest.raises(ValueError, match="condition_state"):
        forecast_status(obligation, condition_state="inconclusive")  # type: ignore[arg-type]


@pytest.mark.parametrize("condition_key", ["", "   "])
def test_obligation_rejects_a_blank_condition_key(condition_key: str) -> None:
    with pytest.raises(ValidationError):
        ConditionalRecurringObligation(
            condition_key=condition_key,
            cadence="monthly",
            due_day=5,
            primary=NativeAmount(amount_minor=4900, source_currency="EUR"),
            fallback=NativeAmount(amount_minor=3900, source_currency="EUR"),
        )


def test_update_rejects_null_primary_but_allows_unknown_fallback() -> None:
    import pytest
    from pydantic import ValidationError

    from app.finance.schemas import ConditionalRecurringObligationUpdate

    with pytest.raises(ValidationError):
        ConditionalRecurringObligationUpdate(primary_amount_minor=None)
    assert ConditionalRecurringObligationUpdate(fallback_amount_minor=None).model_dump(
        exclude_unset=True
    ) == {"fallback_amount_minor": None}


def test_update_rejects_blank_name_and_condition() -> None:
    import pytest
    from pydantic import ValidationError

    from app.finance.schemas import ConditionalRecurringObligationUpdate

    for field in ("name", "condition_key"):
        with pytest.raises(ValidationError):
            ConditionalRecurringObligationUpdate(**{field: "   "})
