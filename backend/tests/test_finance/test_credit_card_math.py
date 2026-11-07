"""No float cents or double counting of installment principal in card limits."""

from datetime import date
from decimal import Decimal

import pytest


@pytest.mark.parametrize(
    "balance,pending,want",
    [
        (-102796, 0, (102796, 3257204, 0, 0)),
        (-3300000, 100000, (3300000, 0, 0, 40000)),
        (10000, 0, (0, 3360000, 10000, 0)),
    ],
)
def test_available_limit_counts_debt_and_holds_not_plan_again(balance, pending, want):
    from app.finance.credit_card_math import card_position

    result = card_position(3360000, balance, pending)
    assert (
        result["debt_pln"],
        result["available_pln"],
        result["overpayment_pln"],
        result["overlimit_pln"],
    ) == want


def test_estimated_schedule_clamps_month_end_and_preserves_every_principal_cent():
    from app.finance.credit_card_math import estimate_schedule

    rows = estimate_schedule(10000, Decimal(12), 3, date(2027, 1, 31), 100)
    assert [r["due_date"] for r in rows] == [
        date(2027, 1, 31),
        date(2027, 2, 28),
        date(2027, 3, 31),
    ]
    assert [r["principal_pln"] for r in rows] == [3333, 3333, 3334]
    assert [r["interest_pln"] for r in rows] == [100, 67, 33]
    assert [r["fees_pln"] for r in rows] == [100, 0, 0]


def test_each_plan_rate_is_independent_and_zero_percent_is_supported():
    from app.finance.credit_card_math import estimate_schedule

    assert estimate_schedule(10000, Decimal(0), 1, date(2026, 12, 12), 0)[0]["interest_pln"] == 0
    assert (
        estimate_schedule(10000, Decimal("10.99"), 1, date(2026, 12, 12), 0)[0]["interest_pln"]
        == 92
    )
    assert (
        estimate_schedule(10000, Decimal("14.50"), 1, date(2026, 12, 12), 0)[0]["interest_pln"]
        == 121
    )


def test_simple_daily_interest_is_an_explicit_estimate_not_a_grace_calculator():
    from app.finance.credit_card_math import estimate_daily_interest

    assert estimate_daily_interest(100000, Decimal("14.50"), 30) == 1192
    assert estimate_daily_interest(0, Decimal("14.50"), 30) == 0


@pytest.mark.parametrize(
    "principal,rate,count",
    [(0, "12", 3), (100, "NaN", 3), (100, "-1", 3), (1, "1", 2), (100, "12", 0)],
)
def test_invalid_plan_inputs_do_not_produce_a_misleading_schedule(principal, rate, count):
    from app.finance.credit_card_math import estimate_schedule

    with pytest.raises(ValueError):
        estimate_schedule(principal, Decimal(rate), count, date(2026, 12, 12), 0)


@pytest.mark.parametrize(
    "changes",
    [
        {"apr": "NaN"},
        {"apr": "Infinity"},
        {"limit_pln": 0},
        {"limit_pln": True},
        {"cycle_close_day": 32},
        {"due_day": 0},
        {"grace_days": -1},
        {"surprise": 1},
    ],
)
def test_card_profile_rejects_unsafe_amounts_rates_and_unknown_fields(changes):
    from pydantic import ValidationError

    from app.finance.credit_card_schemas import CardConfig

    payload = {
        "limit_pln": 3360000,
        "apr": "14.50",
        "cycle_close_day": 17,
        "due_day": 12,
        "grace_days": 57,
        "expected_version": 0,
    }
    with pytest.raises(ValidationError):
        CardConfig(**{**payload, **changes})


def test_payment_allocation_requires_exactly_one_target_and_matching_components():
    import uuid

    from pydantic import ValidationError

    from app.finance.credit_card_schemas import AllocationCreate

    base = {"request_id": uuid.uuid4(), "transaction_id": uuid.uuid4(), "amount_pln": 100}
    for changes in [
        {},
        {"plan_id": uuid.uuid4(), "statement_id": uuid.uuid4()},
        {"plan_id": uuid.uuid4(), "principal_pln": 50},
        {"statement_id": uuid.uuid4(), "interest_pln": 10},
    ]:
        with pytest.raises(ValidationError):
            AllocationCreate(**base, **changes)


def test_estimates_do_not_overflow_the_api_minor_unit_precision():
    from app.finance.credit_card_math import MAX_MONEY, estimate_daily_interest, estimate_schedule

    with pytest.raises(ValueError):
        estimate_schedule(MAX_MONEY, Decimal(100), 1, date(2026, 12, 12), MAX_MONEY)
    with pytest.raises(ValueError):
        estimate_daily_interest(MAX_MONEY, Decimal(100), 3660)
