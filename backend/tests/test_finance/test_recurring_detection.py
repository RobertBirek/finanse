"""Pure, conservative recurrence analysis never writes schedules or ledger data."""

import uuid
from datetime import date

from app.finance.imports.recurring_detection import (
    VerifiedExpenseObservation,
    analyze_new_recurring_schedule,
)

OWNER = uuid.UUID(int=1)
ACCOUNT = uuid.UUID(int=2)


def observation(
    identity: str,
    occurred_on: date,
    description: str = "NETFLIX.COM",
    amount_minor: int = -4900,
    source: str = "bank_import",
    *,
    owner_id: uuid.UUID = OWNER,
    account_id: uuid.UUID = ACCOUNT,
    currency: str = "PLN",
    economic_identity: str | None = None,
    economic_identity_state: str = "canonical",
) -> VerifiedExpenseObservation:
    return VerifiedExpenseObservation(
        owner_id=owner_id,
        account_id=account_id,
        currency=currency,
        source=source,
        strong_identity=identity,
        occurred_on=occurred_on,
        description=description,
        amount_minor=amount_minor,
        economic_identity=economic_identity or f"economic:{identity}",
        economic_identity_state=economic_identity_state,
    )


def test_monthly_verified_expenses_propose_only_a_new_schedule_with_provenance() -> None:
    current = observation("bank:3", date(2026, 3, 3))
    result = analyze_new_recurring_schedule(
        current,
        [
            observation("actual:1", date(2026, 1, 3), source="actual"),
            observation("bank:2", date(2026, 2, 2)),
        ],
    )

    assert result.status == "proposed"
    assert result.proposal is not None
    assert result.proposal.target == "new_schedule"
    assert result.proposal.frequency == "monthly"
    assert result.proposal.amount_kind == "stable"
    assert result.proposal.currency == "PLN"
    assert result.proposal.amount_minor == -4900
    assert result.proposal.formal_deadline is None
    assert [item.strong_identity for item in result.evidence] == [
        "actual:1",
        "bank:2",
        "bank:3",
    ]
    assert [item.source for item in result.evidence] == ["actual", "bank_import", "bank_import"]


def test_annual_verified_expenses_never_become_monthly() -> None:
    current = observation("bank:2026", date(2026, 6, 15), description="DOMAIN HOSTING")
    result = analyze_new_recurring_schedule(
        current,
        [
            observation(
                "bank:2024",
                date(2024, 6, 14),
                description="DOMAIN HOSTING",
            ),
            observation(
                "actual:2025",
                date(2025, 6, 15),
                description="DOMAIN HOSTING",
                source="actual",
            ),
        ],
    )

    assert result.status == "proposed"
    assert result.proposal is not None
    assert result.proposal.frequency == "annual"
    assert result.proposal.amount_minor == -4900


def test_annual_cadence_allows_day_tolerance_across_a_leap_month_boundary() -> None:
    result = analyze_new_recurring_schedule(
        observation("bank:2028", date(2028, 3, 1), description="DOMAIN HOSTING"),
        [
            observation(
                "bank:2026",
                date(2026, 2, 27),
                description="DOMAIN HOSTING",
            ),
            observation(
                "bank:2027",
                date(2027, 2, 28),
                description="DOMAIN HOSTING",
            ),
        ],
    )

    assert result.status == "proposed"
    assert result.proposal is not None
    assert result.proposal.frequency == "annual"


def test_variable_amounts_are_explicitly_marked_not_silently_stabilized() -> None:
    current = observation("bank:3", date(2026, 3, 3), amount_minor=-5300)
    result = analyze_new_recurring_schedule(
        current,
        [
            observation("bank:1", date(2026, 1, 3), amount_minor=-4900),
            observation("actual:2", date(2026, 2, 2), amount_minor=-5100, source="actual"),
        ],
    )

    assert result.status == "proposed"
    assert result.proposal is not None
    assert result.proposal.amount_kind == "variable"
    assert result.proposal.amount_minor is None
    assert result.proposal.currency == "PLN"


def test_fewer_than_three_verified_observations_are_blocked() -> None:
    result = analyze_new_recurring_schedule(
        observation("bank:2", date(2026, 2, 2)),
        [observation("bank:1", date(2026, 1, 3))],
    )

    assert result.status == "blocked"
    assert result.proposal is None
    assert result.reason == "insufficient_verified_observations"


def test_missing_or_reused_strong_identity_is_uncertain_not_deduplicated() -> None:
    current = observation("bank:overlap", date(2026, 3, 3))
    missing_identity = observation("", date(2026, 1, 3))
    result = analyze_new_recurring_schedule(
        current,
        [missing_identity, observation("bank:overlap", date(2026, 2, 2))],
    )

    assert result.status == "uncertain"
    assert result.proposal is None
    assert result.reason == "identity_uncertain"


def test_nfkc_equivalent_canonical_duplicate_is_uncertain_not_dropped() -> None:
    """A byte-distinct merchant spelling cannot hide a reused canonical identity."""
    result = analyze_new_recurring_schedule(
        observation("bank:current", date(2026, 3, 3), description="NETFLIX"),
        [
            observation("bank:duplicate", date(2026, 1, 3), description="ＮＥＴＦＬＩＸ"),
            observation("bank:duplicate", date(2026, 2, 3), description="NETFLIX"),
        ],
    )

    assert result.status == "uncertain"
    assert result.proposal is None
    assert result.reason == "identity_uncertain"


def test_foreign_scope_and_non_bank_current_expense_are_uncertain() -> None:
    foreign = observation("actual:1", date(2026, 1, 3), source="actual", owner_id=uuid.UUID(int=9))
    result = analyze_new_recurring_schedule(
        observation("actual:current", date(2026, 3, 3), source="actual"),
        [foreign, observation("bank:2", date(2026, 2, 2))],
    )

    assert result.status == "uncertain"
    assert result.proposal is None
    assert result.reason == "scope_or_current_source_uncertain"


def test_unrelated_or_variable_merchant_tokens_do_not_form_a_group() -> None:
    result = analyze_new_recurring_schedule(
        observation("bank:3", date(2026, 3, 3), description="NETFLIX 9831"),
        [
            observation("bank:1", date(2026, 1, 3), description="NETFLIX 1234"),
            observation("bank:2", date(2026, 2, 2), description="SPOTIFY", source="actual"),
        ],
    )

    assert result.status == "blocked"
    assert result.proposal is None
    assert result.reason == "insufficient_verified_observations"


def test_gaps_outside_supported_monthly_and_annual_ranges_are_blocked() -> None:
    result = analyze_new_recurring_schedule(
        observation("bank:3", date(2026, 4, 15)),
        [
            observation("bank:1", date(2026, 1, 3)),
            observation("actual:2", date(2026, 2, 2), source="actual"),
        ],
    )

    assert result.status == "blocked"
    assert result.proposal is None
    assert result.reason == "unsupported_cadence"


def test_cross_source_rows_with_one_canonical_economic_identity_are_uncertain() -> None:
    result = analyze_new_recurring_schedule(
        observation("bank:3", date(2026, 3, 3)),
        [
            observation(
                "actual:1",
                date(2026, 1, 3),
                source="actual",
                economic_identity="economic:one",
            ),
            observation("bank:2", date(2026, 2, 2), economic_identity="economic:one"),
        ],
    )

    assert result.status == "uncertain"
    assert result.proposal is None
    assert result.reason == "economic_identity_collision"
    assert [item.strong_identity for item in result.evidence] == ["actual:1", "bank:2", "bank:3"]


def test_unknown_economic_identity_fails_closed_with_bounded_safe_evidence() -> None:
    result = analyze_new_recurring_schedule(
        observation("bank:7", date(2026, 7, 3)),
        [observation(f"bank:{month}", date(2026, month, 3)) for month in range(1, 7)]
        + [
            observation(
                "actual:unknown",
                date(2025, 12, 3),
                source="actual",
                economic_identity_state="unknown",
            )
        ],
    )

    assert result.status == "uncertain"
    assert result.reason == "economic_identity_uncertain"
    assert len(result.evidence) == 5
    assert "description" not in result.evidence[0].model_dump()


def test_calendar_consecutive_months_allow_short_february_but_not_four_weekly_pattern() -> None:
    calendar_monthly = analyze_new_recurring_schedule(
        observation("bank:mar", date(2026, 3, 31)),
        [
            observation("actual:jan", date(2026, 1, 31), source="actual"),
            observation("bank:feb", date(2026, 2, 28)),
        ],
    )
    four_weekly = analyze_new_recurring_schedule(
        observation("bank:week-3", date(2026, 2, 26)),
        [
            observation("actual:week-1", date(2026, 1, 1), source="actual"),
            observation("bank:week-2", date(2026, 1, 29)),
        ],
    )

    assert calendar_monthly.proposal is not None
    assert calendar_monthly.proposal.frequency == "monthly"
    assert four_weekly.status == "uncertain"
    assert four_weekly.reason == "cadence_ambiguous_four_weekly"


def test_non_anchored_eleven_month_intervals_are_not_annual() -> None:
    result = analyze_new_recurring_schedule(
        observation("bank:2025-11", date(2025, 11, 1)),
        [
            observation("actual:2024-01", date(2024, 1, 1), source="actual"),
            observation("bank:2024-12", date(2024, 12, 1)),
        ],
    )

    assert result.status == "blocked"
    assert result.proposal is None
    assert result.reason == "unsupported_cadence"


def test_backdated_current_expense_is_uncertain() -> None:
    result = analyze_new_recurring_schedule(
        observation("bank:current", date(2026, 2, 3)),
        [
            observation("actual:old", date(2026, 1, 3), source="actual"),
            observation("bank:later", date(2026, 3, 3)),
        ],
    )

    assert result.status == "uncertain"
    assert result.proposal is None
    assert result.reason == "current_not_latest"
