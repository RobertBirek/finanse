"""Source contracts reject lossy values before staging or ledger decisions exist."""

import datetime as dt

import pytest
from pydantic import ValidationError

from app.finance.imports.contracts import (
    Check,
    ParsedSchedule,
    ParsedStatement,
    ScheduleRow,
    SourcePosition,
    StatementRow,
)


def statement_row(**changes: object) -> StatementRow:
    values: dict[str, object] = {
        "key": "page-1-line-4",
        "position": {"page": 1, "line": 4, "section": None},
        "booking_date": "2026-01-03",
        "operation_date": None,
        "started_at": None,
        "completed_at": None,
        "description": "Syntetyczny zakup",
        "amount": -100,
        "fee": 0,
        "currency": "PLN",
        "state": "posted",
        "balance_after": None,
        "bank_reference": None,
        "raw": {"Kwota": "-1,00", "Saldo": ""},
    }
    return StatementRow.model_validate(values | changes)


def parsed_statement(**changes: object) -> ParsedStatement:
    values: dict[str, object] = {
        "kind": "statement",
        "bank": "velo",
        "layout": "velo_account_v1",
        "parser_version": "1",
        "account_reference": "synthetic-account-reference",
        "currency": "PLN",
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
        "opening": 1000,
        "closing": 800,
        "rows": [
            statement_row(key="row-1", balance_after=900),
            statement_row(key="row-2", balance_after=800),
        ],
        "checks": [
            {
                "code": "closing",
                "required": True,
                "result": "passed",
                "expected": 800,
                "actual": 800,
            }
        ],
        "warnings": [],
        "card_header": None,
    }
    return ParsedStatement.model_validate(values | changes)


def test_missing_balance_is_not_coerced_to_zero() -> None:
    assert statement_row().balance_after is None
    assert statement_row(balance_after=0).balance_after == 0
    assert statement_row().raw["Saldo"] == ""


@pytest.mark.parametrize("field", ["amount", "fee", "balance_after"])
@pytest.mark.parametrize("value", [True, False, 1.0, "100", 9007199254740992])
def test_lossy_or_unsafe_minor_unit_value_is_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        statement_row(**{field: value})


def test_repeated_real_purchases_keep_separate_occurrences() -> None:
    parsed = parsed_statement()
    restored = ParsedStatement.model_validate(parsed.model_dump(mode="json"))
    assert len(restored.rows) == 2
    assert [row.amount for row in restored.rows] == [-100, -100]
    assert [row.balance_after for row in restored.rows] == [900, 800]
    assert [row.key for row in restored.rows] == ["row-1", "row-2"]


def test_duplicate_source_position_keys_are_rejected() -> None:
    repeated = statement_row(key="same-row")
    with pytest.raises(ValidationError):
        parsed_statement(rows=[repeated, repeated])


def test_foreign_row_cannot_silently_join_pln_statement() -> None:
    with pytest.raises(ValidationError):
        parsed_statement(rows=[statement_row(currency="EUR")])


@pytest.mark.parametrize("bank", ["citi", "unknown", ""])
def test_unapproved_bank_cannot_enter_normalized_statement(bank: str) -> None:
    with pytest.raises(ValidationError):
        parsed_statement(bank=bank)


def test_zero_activity_statement_does_not_invent_a_transaction() -> None:
    parsed = parsed_statement(opening=0, closing=0, rows=[], checks=[])
    assert parsed.rows == []
    assert parsed.opening == parsed.closing == 0


def test_inverted_statement_period_is_rejected() -> None:
    with pytest.raises(ValidationError):
        parsed_statement(period_start="2026-02-01", period_end="2026-01-31")


def test_negative_fee_retains_refund_direction() -> None:
    row = statement_row(amount=105, fee=-5, balance_after=1105)
    assert row.amount == 105 and row.fee == -5
    assert row.raw["Kwota"] == "-1,00"


@pytest.mark.parametrize("date", ["2026-02-30", "2026-01-03T00:00:00", "03.01.2026"])
def test_normalized_booking_date_requires_calendar_iso_date(date: str) -> None:
    with pytest.raises(ValidationError):
        statement_row(booking_date=date)


def schedule_row(**changes: object) -> ScheduleRow:
    values: dict[str, object] = {
        "bank_number": 1,
        "due_date": "2026-03-16",
        "principal": 90000,
        "interest": 9000,
        "fees": 1000,
        "total": 100000,
        "balance_after": 0,
        "position": {"page": 2, "line": 10, "section": "schedule"},
    }
    return ScheduleRow.model_validate(values | changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"principal": -1},
        {"interest": -1},
        {"fees": None},
        {"total": 99999},
        {"bank_number": 0},
        {"principal": True},
        {"balance_after": -1},
        {"principal": 9007199254740991, "total": 9007199254750991},
        {"principal": 0, "interest": 0, "fees": 0, "total": 0},
    ],
)
def test_schedule_inconsistent_components_cannot_become_a_plan(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        schedule_row(**changes)


def test_bank_number_is_not_an_existing_installment_identifier() -> None:
    row = schedule_row()
    assert row.bank_number == 1
    assert row.total == 100000
    with pytest.raises(ValidationError):
        schedule_row(installment_id="untrusted-client-identifier")


def test_schedule_contract_preserves_missing_effective_date_for_review() -> None:
    parsed = ParsedSchedule(
        bank="velo",
        layout="velo_schedule_v1",
        parser_version="1",
        loan_reference=None,
        effective_date=None,
        rows=[schedule_row()],
        complete_tail=False,
        checks=[
            Check(
                code="effective_date",
                required=True,
                result="unavailable",
                expected=None,
                actual=None,
            )
        ],
        warnings=["missing_effective_date"],
    )
    assert parsed.effective_date is None and not parsed.complete_tail
    assert parsed.rows[0].due_date == dt.date(2026, 3, 16)
    assert parsed.checks[0].result == "unavailable"


def test_source_position_remains_page_and_line_not_a_transaction_id() -> None:
    position = SourcePosition(page=2, line=10, section="schedule")
    assert position.page == 2 and position.line == 10
    with pytest.raises(ValidationError):
        SourcePosition(page=0, line=10, section=None)
