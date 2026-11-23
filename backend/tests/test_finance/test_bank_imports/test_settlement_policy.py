import uuid
from datetime import date, timedelta

from app.finance.imports.settlement_policy import (
    Match,
    distinct_category,
    repeated_targets,
    settlement_kind,
    strict_match,
)
from tests.test_finance.test_bank_imports.test_contracts import statement_row


def test_current_card_purchases_and_explicit_interest_are_supported() -> None:
    for label in ("ZAKUP", "ODSETKI OD TRANSAKCJI GOTOWKOWYCH"):
        row = statement_row(amount=-499).model_copy(
            update={"raw": {"description_lines": [label, "na kwotę -4,99 PLN"]}}
        )
        assert settlement_kind("velo", "velo_card_v1", row) == "expense"


def test_honda_cash_and_fees_repayment_and_installment_principal_stay_open() -> None:
    for label in (
        "CASH WITHDRAWAL",
        "Prowizja za transakcję szczególną",
        "Spłata",
        "Przelew na Raty",
    ):
        row = statement_row(amount=-220000).model_copy(
            update={"raw": {"description_lines": [label, "na kwotę -2 200,00 PLN"]}}
        )
        assert settlement_kind("velo", "velo_card_v1", row) is None
    principal = statement_row(amount=-86538).model_copy(
        update={
            "raw": {
                "description_lines": ["Plan Spłat Ratalnych „Komfort”", "Część kapitałowa raty"]
            }
        }
    )
    assert settlement_kind("velo", "velo_card_v1", principal) is None


def test_matching_needs_one_exact_movement_and_semantic_evidence() -> None:
    row = statement_row(amount=-100)
    target = uuid.uuid4()
    weak = Match(target, "expense", "Inny zakup", row.booking_date, -100, False)
    assert strict_match(row, [weak], set()) is None
    exact = Match(target, "expense", row.description, row.booking_date, -100, False)
    assert strict_match(row, [exact], set()) == exact
    assert strict_match(row, [exact, weak], set()) is None
    assert strict_match(row, [exact], {target}) is None
    assert (
        strict_match(
            row, [Match(target, "expense", row.description, date(2026, 1, 20), -100, True)], set()
        )
        is None
    )
    assert row.booking_date is not None
    assert (
        strict_match(
            row,
            [
                Match(
                    target,
                    "expense",
                    row.description,
                    row.booking_date + timedelta(days=1),
                    -100,
                    False,
                )
            ],
            set(),
        )
        is None
    )
    assert (
        strict_match(
            row, [Match(target, "expense", row.description, row.booking_date, -101, True)], set()
        )
        is None
    )


def test_repeated_targets_and_categories_never_select_by_guess() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    assert repeated_targets([a, b, a]) == {a}
    assert distinct_category([a, a]) == a
    assert distinct_category([a, b]) is None
    assert distinct_category([]) is None


def test_used_transaction_is_ineligible_even_with_a_strong_reference() -> None:
    row = statement_row(bank_reference="synthetic-ref")
    target = uuid.uuid4()
    strong = Match(target, "expense", "Other description", row.booking_date, row.amount, True)
    assert strict_match(row, [strong], set()) == strong
    assert strict_match(row, [strong], {target}) is None


def test_matching_ignores_only_known_bank_and_actual_description_wrappers() -> None:
    row = statement_row(
        description="ZAKUP\nna kwotę -1,00 PLN - Nazwa sklepu",
        raw={"description_lines": ["ZAKUP", "na kwotę -1,00 PLN - Nazwa sklepu"]},
    )
    imported = Match(
        uuid.uuid4(),
        "expense",
        "[actual:00000000-0000-4000-8000-000000000001] Nazwa sklepu",
        row.booking_date,
        row.amount,
        False,
    )
    assert strict_match(row, [imported], set()) == imported
