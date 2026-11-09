import hashlib
from datetime import date

import pytest

from app.finance.imports.contracts import ParserInput
from app.finance.imports.errors import ImportError
from app.finance.imports.parsers.registry import parse_import
from app.finance.imports.parsers.velo_account import parse_velo_account
from app.finance.imports.pdf_text import PdfLimits, extract_pdf_pages
from tests.test_finance.test_bank_imports.factories import text_pdf_bytes

COLUMNS = "Data\nksięgowania\nData\ntransakcji\nOpis transakcji Kwota transakcji\nw PLN\nSaldo po transakcji\nw PLN"
HEADER = (
    "VeloBank S.A.\nWyciąg nr 1/2026\nWyciąg za okres od 2026.01.01 do 2026.01.31\n"
    "Numer rachunku: 00 0000 0000 0000 0000 0000 0000\nWaluta rachunku: PLN\n"
    + COLUMNS
    + "\nSaldo początkowe   1 000,00\n"
)
FIRST = "2026.01.02\n2026.01.01\nSynthetic purchase\n-10,00\n990,00\n"
SECOND = "2026.01.03\n2026.01.02\nSynthetic transfer\n25,00\n1 015,00\n"
SUMMARY = "Obroty WN\nObroty MA\nSaldo końcowe\n-10,00\n25,00\n1 015,00\nObroty WN - suma obciążeń rachunku\nObroty MA - suma uznań rachunku\n"


def source(*pages: str) -> ParserInput:
    raw = "\n".join(pages).encode()
    return ParserInput(
        content=raw,
        pages=pages,
        mime_type="application/pdf",
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def failed_required(result) -> list[str]:
    return [check.code for check in result.checks if check.required and check.result != "passed"]


def test_velo_account_keeps_dates_direction_balances_and_source_positions() -> None:
    result = parse_velo_account(source(HEADER + FIRST + SECOND + SUMMARY))
    assert result.bank == "velo" and result.currency == "PLN" and not failed_required(result)
    assert result.period_start == date(2026, 1, 1) and result.period_end == date(2026, 1, 31)
    assert result.opening == 100000 and result.closing == 101500
    assert [row.amount for row in result.rows] == [-1000, 2500]
    assert [row.balance_after for row in result.rows] == [99000, 101500]
    assert all(row.fee == 0 and row.state == "posted" for row in result.rows)
    assert result.rows[0].booking_date == date(2026, 1, 2)
    assert result.rows[0].operation_date == date(2026, 1, 1)
    assert result.rows[0].position.page == 1 and result.rows[0].position.line > 1
    assert result.account_reference == "00000000000000000000000000"
    assert parse_import(source(HEADER + FIRST + SECOND + SUMMARY), "statement") == result


def test_actual_polish_text_pdf_is_extracted_by_bounded_pypdf_before_parsing() -> None:
    raw = text_pdf_bytes(HEADER + FIRST + SECOND + SUMMARY)
    pages = extract_pdf_pages(
        raw,
        PdfLimits(
            max_bytes=1024 * 1024,
            max_pages=10,
            max_text_chars=20000,
            timeout_seconds=5,
            max_memory_bytes=256 * 1024 * 1024,
        ),
    )
    assert "Saldo początkowe" in pages[0] and "księgowania" in pages[0]
    result = parse_velo_account(
        ParserInput(
            content=raw,
            pages=pages,
            mime_type="application/pdf",
            sha256=hashlib.sha256(raw).hexdigest(),
        )
    )
    assert len(result.rows) == 2 and not failed_required(result)


@pytest.mark.parametrize(
    "direction,amount,closing,totals",
    [
        ("WN", -1000, "990,00", "-10,00\n0,00"),
        ("MA", 1000, "1 010,00", "0,00\n10,00"),
    ],
)
def test_explicit_bank_wn_ma_direction_is_not_income_expense_classification(
    direction: str,
    amount: int,
    closing: str,
    totals: str,
) -> None:
    body = f"2026.01.02\n2026.01.01\nSynthetic operation\n10,00 {direction}\n{closing}\n"
    summary = f"Obroty WN\nObroty MA\nSaldo końcowe\n{totals}\n{closing}\n"
    result = parse_velo_account(source(HEADER + body + summary))
    assert result.rows[0].amount == amount and not failed_required(result)


def test_page_break_can_put_amounts_before_description_without_losing_the_row() -> None:
    first = HEADER + "2026.01.02\n2026.01.01\n-10,00\n990,00\n"
    second = COLUMNS + "\nSynthetic purchase\n" + SECOND + SUMMARY
    result = parse_velo_account(source(first, second))
    assert len(result.rows) == 2 and not failed_required(result)
    assert result.rows[0].description == "Synthetic purchase"
    assert result.rows[0].position.page == 1 and result.rows[1].position.page == 2


def test_known_bank_footer_is_not_folded_into_the_payment_description() -> None:
    footer = "Infolinia +00 000 000 000\nVeloBank S.A. z siedzibą w Warszawie\nvelobank.pl\n"
    result = parse_velo_account(source(HEADER + FIRST + footer, SECOND + SUMMARY))
    assert not failed_required(result) and result.rows[0].description == "Synthetic purchase"


@pytest.mark.parametrize("tail", ["", "2026.01.03\n2026.01.02\nIncomplete row\n25,00\n"])
def test_truncated_velo_statement_is_not_ready(tail: str) -> None:
    result = parse_velo_account(source(HEADER + FIRST + tail))
    assert failed_required(result)
    assert [row.amount for row in result.rows] == [-1000]


@pytest.mark.parametrize(
    "changes",
    [
        ("-10,00\n25,00\n1 015,00", "-11,00\n25,00\n1 015,00"),
        ("990,00", "991,00"),
        ("1 015,00", "1 016,00"),
    ],
)
def test_conflicting_row_or_summary_amounts_are_blocked_not_repaired(
    changes: tuple[str, str],
) -> None:
    original = HEADER + FIRST + SECOND + SUMMARY
    result = parse_velo_account(source(original.replace(*changes)))
    assert failed_required(result)
    assert result.rows[0].amount == -1000


def test_unknown_standalone_financial_line_cannot_hide_in_a_description() -> None:
    bad = FIRST.replace("Synthetic purchase", "Synthetic purchase\n7,77")
    result = parse_velo_account(source(HEADER + bad + SECOND + SUMMARY))
    assert failed_required(result)


def test_adjacent_period_does_not_create_a_missing_transfer_or_opening_adjustment() -> None:
    previous = parse_velo_account(source(HEADER + FIRST + SECOND + SUMMARY))
    later_header = HEADER.replace("2026.01.01 do 2026.01.31", "2026.02.01 do 2026.02.28")
    later = parse_velo_account(
        source(later_header + "Obroty WN\nObroty MA\nSaldo końcowe\n0,00\n0,00\n1 000,00\n")
    )
    assert previous.closing != later.opening and later.rows == [] and not failed_required(later)


def test_unknown_velo_layout_does_not_guess_a_table_from_financial_numbers() -> None:
    with pytest.raises(ImportError):
        parse_velo_account(source("VeloBank\nUnknown layout\n-10,00\n990,00"))


@pytest.mark.parametrize(
    "extra", ["2026.01.04\n2026.01.03\nSynthetic lost row\n-1,00\n1 014,00\n", "7,77\n"]
)
def test_financial_data_after_summary_is_not_silently_ignored(extra: str) -> None:
    result = parse_velo_account(source(HEADER + FIRST + SECOND + SUMMARY + extra))
    assert failed_required(result)


def test_unrecognized_column_contract_does_not_guess_amount_and_balance() -> None:
    with pytest.raises(ImportError):
        parse_velo_account(
            source(
                (HEADER + FIRST + SECOND + SUMMARY).replace(
                    "Opis transakcji Kwota transakcji", "Unknown columns"
                )
            )
        )
