import csv
import hashlib
import io
from datetime import date
from pathlib import Path

import pytest

from app.finance.imports.contracts import ParserInput
from app.finance.imports.errors import ImportError
from app.finance.imports.parsers.money import parse_minor_units
from app.finance.imports.parsers.registry import parse_import
from app.finance.imports.parsers.revolut_csv import parse_revolut_csv

FIXTURES = Path(__file__).parent / "fixtures"
HEADERS = [
    "Rodzaj",
    "Produkt",
    "Data rozpoczęcia",
    "Data zrealizowania",
    "Opis",
    "Kwota",
    "Opłata",
    "Waluta",
    "State",
    "Saldo",
]


def parser_input(content: bytes) -> ParserInput:
    return ParserInput(
        content=content,
        pages=None,
        mime_type="text/csv",
        sha256=hashlib.sha256(content).hexdigest(),
    )


def csv_source(*changes: dict[str, str], bom: bool = False) -> ParserInput:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, HEADERS)
    writer.writeheader()
    for index, change in enumerate(changes):
        writer.writerow(
            {
                "Rodzaj": "Przelew",
                "Produkt": "Bieżący",
                "Data rozpoczęcia": f"2026-01-0{index + 1} 10:00:00",
                "Data zrealizowania": f"2026-01-0{index + 1} 10:00:00",
                "Opis": "Synthetic",
                "Kwota": "0.00",
                "Opłata": "0.00",
                "Waluta": "PLN",
                "State": "ZAKOŃCZONO",
                "Saldo": "10.00",
                **change,
            }
        )
    return parser_input(stream.getvalue().encode("utf-8-sig" if bom else "utf-8"))


def failed_required(result) -> list[str]:
    return [check.code for check in result.checks if check.required and check.result != "passed"]


@pytest.mark.parametrize(
    "value,separator,expected",
    [
        ("12.34", ".", 1234),
        ("-12.34", ".", -1234),
        ("+12.34", ".", 1234),
        ("1 234,56", ",", 123456),
        ("1\u00a0234,56", ",", 123456),
        ("1\u202f234,56", ",", 123456),
        ("0", ".", 0),
        ("-0.00", ".", 0),
        ("90071992547409.91", ".", 9007199254740991),
    ],
)
def test_money_uses_exact_minor_units(value: str, separator: str, expected: int) -> None:
    amount = parse_minor_units(value, decimal_separator=separator)
    assert type(amount) is int and amount == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "NaN",
        "Infinity",
        "1e3",
        "1.",
        ".00",
        "1.2",
        "1.234",
        "12 34.56",
        "1,23",
        "1.00x",
        "90071992547409.92",
        "--1.00",
    ],
)
def test_incomplete_or_ambiguous_money_is_not_rounded_or_guessed(value: str) -> None:
    with pytest.raises(ImportError):
        parse_minor_units(value, decimal_separator=".")


@pytest.mark.parametrize("currency", ["pln", "eur", "usd"])
def test_three_source_currencies_keep_every_original_column(currency: str) -> None:
    source = parser_input((FIXTURES / f"revolut_{currency}.csv").read_bytes())
    result = parse_revolut_csv(source)
    assert result.bank == "revolut" and result.currency == currency.upper()
    assert result.opening == 0 and result.closing == (800 if currency != "usd" else 400)
    assert not failed_required(result)
    assert "opening_derived" in result.warnings and "timestamps_without_timezone" in result.warnings
    assert result.account_reference is None
    assert all(set(row.raw) == set(HEADERS) for row in result.rows)
    assert parse_import(source, "statement") == result


def test_same_description_amount_keeps_two_real_purchases() -> None:
    result = parse_revolut_csv(parser_input((FIXTURES / "revolut_pln.csv").read_bytes()))
    purchases = result.rows[1:]
    assert [row.amount for row in purchases] == [-100, -100]
    assert [row.balance_after for row in purchases] == [900, 800]
    assert len({row.key for row in purchases}) == 2
    assert purchases[0].started_at == "2026-01-02 10:00:00"
    assert purchases[0].completed_at == "2026-01-02 10:00:01"
    assert purchases[0].booking_date == date(2026, 1, 2)


def test_fee_is_separate_from_exported_amount_and_account_delta_matches_balance() -> None:
    result = parse_revolut_csv(parser_input((FIXTURES / "revolut_fee_excluded.csv").read_bytes()))
    row = result.rows[1]
    assert (row.amount, row.fee, row.amount + row.fee) == (-120, 20, -100)
    assert row.raw["Kwota"] == "-1.00" and row.raw["Opłata"] == "0.20"
    assert result.closing == 880 and not failed_required(result)


def test_incompatible_fee_semantics_stay_blocked_not_adjusted_to_make_totals_fit() -> None:
    result = parse_revolut_csv(
        parser_input((FIXTURES / "revolut_fee_included_wrong_contract.csv").read_bytes())
    )
    assert result.rows[1].amount == -140 and result.rows[1].fee == 20
    assert failed_required(result)


def test_overlap_retains_real_occurrences_without_deduplicating_purchases() -> None:
    full = (FIXTURES / "revolut_pln.csv").read_bytes()
    lines = full.splitlines(keepends=True)
    complete = parse_revolut_csv(parser_input(full))
    overlap = parse_revolut_csv(parser_input(lines[0] + b"".join(lines[2:])))
    assert len(overlap.rows) == 2
    assert [row.raw for row in complete.rows[1:]] == [row.raw for row in overlap.rows]
    assert overlap.opening == 1000 and overlap.closing == 800


def test_reverse_export_checks_balances_chronologically_but_preserves_source_order() -> None:
    lines = (FIXTURES / "revolut_pln.csv").read_bytes().splitlines(keepends=True)
    result = parse_revolut_csv(parser_input(lines[0] + b"".join(reversed(lines[1:]))))
    assert [row.amount for row in result.rows] == [-100, -100, 1000]
    assert result.opening == 0 and result.closing == 800 and not failed_required(result)
    assert [row.position.line for row in result.rows] == [2, 3, 4]


def test_bom_quotes_embedded_newlines_and_formulas_are_original_text() -> None:
    result = parse_revolut_csv(csv_source({"Opis": '=SUM(1+2), "quoted"\nnext line'}, bom=True))
    assert result.rows[0].description == '=SUM(1+2), "quoted"\nnext line'
    assert result.rows[0].position.line == 2 and result.rows[0].amount == 0


@pytest.mark.parametrize(
    "state,normalized",
    [("PENDING", "pending"), ("REVERTED", "reverted"), ("CANCELLED", "cancelled")],
)
def test_unposted_states_remain_visible_without_fake_posting_dates(
    state: str, normalized: str
) -> None:
    result = parse_revolut_csv(
        csv_source({"State": state, "Data zrealizowania": "", "Saldo": "", "Kwota": "-2.00"})
    )
    assert result.rows[0].state == normalized and result.rows[0].booking_date is None
    assert result.rows[0].balance_after is None
    assert result.opening is None and result.closing is None


def test_unknown_state_is_retained_but_never_guessed_as_posted() -> None:
    result = parse_revolut_csv(csv_source({"State": "NEW_BANK_STATE"}))
    assert result.rows[0].state == "unknown" and result.rows[0].raw["State"] == "NEW_BANK_STATE"
    assert "known_states" in failed_required(result)


def test_information_only_zero_movement_requires_unchanged_source_balance() -> None:
    result = parse_revolut_csv(csv_source({}, {}))
    assert [row.amount for row in result.rows] == [0, 0] and not failed_required(result)
    broken = parse_revolut_csv(csv_source({}, {"Saldo": "11.00"}))
    assert failed_required(broken)


@pytest.mark.parametrize(
    "changes",
    [
        {"Saldo": ""},
        {"Data zrealizowania": ""},
        {"Kwota": "1.234"},
        {"Opłata": ""},
        {"Waluta": "GBP"},
        {"Data zrealizowania": "2026-01-01T10:00:00+02:00"},
        {"Data zrealizowania": "2026-02-30 10:00:00"},
    ],
)
def test_malformed_completed_records_cannot_be_silently_skipped(changes: dict[str, str]) -> None:
    with pytest.raises(ImportError):
        parse_revolut_csv(csv_source(changes))


def test_mixed_currencies_cannot_be_hidden_in_one_account_statement() -> None:
    with pytest.raises(ImportError) as error:
        parse_revolut_csv(csv_source({}, {"Waluta": "EUR"}))
    assert error.value.code == "csv_mixed_currencies"


def test_equal_timestamp_occurrences_use_balance_chain_without_changing_amounts() -> None:
    result = parse_revolut_csv(
        csv_source(
            {"Kwota": "-1.00", "Saldo": "8.00"},
            {
                "Data rozpoczęcia": "2026-01-01 10:00:00",
                "Data zrealizowania": "2026-01-01 10:00:00",
                "Kwota": "-1.00",
                "Saldo": "9.00",
            },
        )
    )
    assert [row.amount for row in result.rows] == [-100, -100]
    assert result.opening == 1000 and result.closing == 800 and not failed_required(result)
    assert "order_from_balances" in result.warnings


def test_complete_header_contract_is_not_tied_to_column_order() -> None:
    original = csv_source({"Kwota": "-1.00", "Saldo": "9.00"})
    values = list(csv.reader(io.StringIO(original.content.decode(), newline="")))
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerows([list(reversed(row)) for row in values])
    result = parse_import(parser_input(stream.getvalue().encode()), "statement")
    assert result.rows[0].amount == -100 and result.rows[0].raw["Saldo"] == "9.00"


@pytest.mark.parametrize(
    "corruption", ["duplicate_header", "missing_column", "extra_field", "repeat_header"]
)
def test_complete_table_contract_cannot_silently_drop_columns_or_rows(corruption: str) -> None:
    original = csv_source({})
    rows = list(csv.reader(io.StringIO(original.content.decode(), newline="")))
    if corruption == "duplicate_header":
        rows[0][-1] = rows[0][0]
    elif corruption == "missing_column":
        rows[0].pop()
    elif corruption == "extra_field":
        rows[1].append("unexpected")
    else:
        rows.append(rows[0])
    stream = io.StringIO(newline="")
    csv.writer(stream).writerows(rows)
    with pytest.raises(ImportError):
        parse_revolut_csv(parser_input(stream.getvalue().encode()))


@pytest.mark.parametrize(
    "content", [b"", b"wrong,headers\n1,2\n", b"\xff\xfeinvalid", b'Rodzaj,Produkt\n"unterminated']
)
def test_unrecognized_or_truncated_files_return_no_partial_financial_result(content: bytes) -> None:
    with pytest.raises(ImportError):
        parse_revolut_csv(parser_input(content))
