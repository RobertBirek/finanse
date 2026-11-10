"""Bank plan values, not paid transactions: real synthetic PDFs through bounded pypdf."""

import hashlib
from datetime import date
from pathlib import Path

import pytest

from app.finance.imports.contracts import ParsedSchedule, ParserInput
from app.finance.imports.errors import ImportError
from app.finance.imports.parsers.registry import parse_import
from app.finance.imports.pdf_text import PdfLimits, extract_pdf_pages
from tests.test_finance.test_bank_imports.factories import text_pdf_bytes

COLUMNS = "Nr raty: Data raty: Rata kapitałowa (PLN) Rata odsetkowa (PLN) Rata łącznie (PLN)\nSaldo\nzadłużenia kredytu po\nspłacie raty (PLN)"
HEADER = (
    "VeloBank S.A.\nHarmonogram spłaty kredytu\nnumer umowy kredytu SYNTHETIC-001\nod kiedy obowiązuje nowy harmonogram 2026-11-01\n"
    + COLUMNS
    + "\n"
)
ROW1 = "1 2026-12-15 1 000,00 20,00 1 020,00 2 000,00\n"
ROW2 = "2 2027-01-15 1 000,00 10,00 1 010,00 1 000,00\n"
ROW3 = "3 2027-02-15 1 000,00 5,00 1 005,00 0,00\n"
LIMITS = PdfLimits(
    max_bytes=1024 * 1024,
    max_pages=10,
    max_text_chars=40000,
    timeout_seconds=5,
    max_memory_bytes=256 * 1024 * 1024,
)


def source(*pages: str, pdf: bool = False) -> ParserInput:
    raw = text_pdf_bytes(*pages) if pdf else "\n".join(pages).encode()
    extracted = extract_pdf_pages(raw, LIMITS) if pdf else pages
    return ParserInput(raw, extracted, "application/pdf", hashlib.sha256(raw).hexdigest())


def parse(*pages: str, pdf: bool = False) -> ParsedSchedule:
    result = parse_import(source(*pages, pdf=pdf), "loan_schedule")
    assert isinstance(result, ParsedSchedule)
    return result


def failed(result: ParsedSchedule) -> list[str]:
    return [c.code for c in result.checks if c.required and c.result != "passed"]


@pytest.mark.parametrize("wrapped_date", [False, True])
def test_actual_pdf_retains_source_numbers_dates_components_and_positions(wrapped_date):
    header = HEADER.replace("harmonogram 2026", "harmonogram\n2026") if wrapped_date else HEADER
    result = parse(header + ROW1 + "Strona 1 z 2", ROW2 + ROW3 + "Strona 2 z 2", pdf=True)
    assert not failed(result) and result.complete_tail
    assert result.bank == "velo" and result.currency == "PLN"
    assert result.effective_date == date(2026, 11, 1)
    assert result.loan_reference == "SYNTHETIC-001"
    assert [r.bank_number for r in result.rows] == [1, 2, 3]
    assert [r.principal for r in result.rows] == [100000, 100000, 100000]
    assert [r.interest for r in result.rows] == [2000, 1000, 500]
    assert [r.total for r in result.rows] == [102000, 101000, 100500]
    assert [r.balance_after for r in result.rows] == [200000, 100000, 0]
    assert [r.fees for r in result.rows] == [0, 0, 0]
    assert [r.position.page for r in result.rows] == [1, 2, 2]
    assert result.rows[-1].due_date == date(2027, 2, 15)


def test_letter_cover_date_does_not_override_explicit_table_effective_date():
    result = parse(
        "VeloBank S.A.\nMiasto, 2026-10-31\nHARMONOGRAM SPŁAT",
        HEADER + ROW1 + ROW2 + ROW3 + "Strona 2 z 2",
    )
    assert result.effective_date == date(2026, 11, 1) and not failed(result)


def test_renumbered_remaining_plan_preserves_bank_number_not_internal_identity():
    result = parse(
        HEADER
        + ROW2.replace("2 2027", "1 2027")
        + ROW3.replace("3 2027", "2 2027")
        + "Strona 1 z 1",
        pdf=True,
    )
    assert result.complete_tail and not failed(result)
    assert [r.bank_number for r in result.rows] == [1, 2]
    assert result.rows[0].due_date == date(2027, 1, 15)


def test_money_wrapped_across_lines_and_repeated_table_header_are_not_lost():
    result = parse(
        HEADER + ROW1.replace("1 000,00", "1\n000,00") + "Strona 1 z 2",
        COLUMNS + "\n" + ROW2 + ROW3 + "Strona 2 z 2",
        pdf=True,
    )
    assert len(result.rows) == 3 and result.rows[0].principal == 100000
    assert not failed(result)


@pytest.mark.parametrize(
    "body",
    [
        HEADER + ROW1 + ROW2 + "Strona 1 z 2",
        HEADER + ROW1 + ROW3 + "Strona 1 z 1",
        HEADER + ROW1 + ROW2 + ROW3.replace("3 2027-02-15", "2 2027-01-15") + "Strona 1 z 1",
        HEADER + ROW1 + ROW2 + ROW3.replace("1 005,00", "1 006,00") + "Strona 1 z 1",
        HEADER + ROW1 + ROW2.replace("1 000,00\n", "999,00\n") + ROW3 + "Strona 1 z 1",
        HEADER + ROW1 + ROW2 + ROW3.replace("1 000,00", "-1 000,00") + "Strona 1 z 1",
        HEADER + ROW1 + ROW2 + ROW3.replace("2027-02-15", "2026-02-15") + "Strona 1 z 1",
        HEADER.replace("od kiedy obowiązuje nowy harmonogram 2026-11-01\n", "")
        + ROW1
        + ROW2
        + ROW3
        + "Strona 1 z 1",
        HEADER.replace("Rata łącznie (PLN)", "Kwota nieznana (PLN)")
        + ROW1
        + ROW2
        + ROW3
        + "Strona 1 z 1",
        HEADER.replace("Saldo\nzadłużenia kredytu po\nspłacie raty (PLN)", "Nieznana kolumna")
        + ROW1
        + ROW2
        + ROW3
        + "Strona 1 z 1",
        HEADER + ROW1 + ROW2 + ROW3,
        HEADER + ROW1 + ROW2 + ROW3 + "Strona 2 z 2",
        HEADER + ROW1 + ROW2 + ROW3 + "UNKNOWN EXTRA ROW\nStrona 1 z 1",
        HEADER.replace("(PLN)", "(EUR)") + ROW1 + ROW2 + ROW3 + "Strona 1 z 1",
    ],
)
def test_incomplete_or_conflicting_plan_never_claims_a_complete_tail(body):
    try:
        result = parse(body)
    except ImportError:
        return  # unsupported/incomplete is safe, never an activation-authorizing parse
    assert failed(result) and not result.complete_tail


def test_explicit_residual_is_preserved_and_not_forced_to_zero():
    row = "1 2026-12-15 1 000,00 20,00 1 020,00 500,00\n"
    result = parse(
        HEADER + row + "Saldo pozostałe po zakończeniu harmonogramu (PLN): 500,00\nStrona 1 z 1"
    )
    assert not failed(result) and result.complete_tail and result.rows[0].balance_after == 50000


def test_unexplained_nonzero_final_balance_is_not_assumed_to_be_a_balloon():
    result = parse(HEADER + ROW1 + ROW2 + "Strona 1 z 1")
    assert not result.complete_tail and failed(result)


def test_unknown_fee_column_cannot_be_silently_defaulted_to_zero():
    try:
        result = parse(
            HEADER.replace("Rata łącznie (PLN)", "Opłaty (PLN) Rata łącznie (PLN)")
            + ROW1
            + ROW2
            + ROW3
            + "Strona 1 z 1"
        )
    except ImportError:
        return
    assert not result.complete_tail and failed(result)


@pytest.mark.parametrize("bank", ["Citi Handlowy", "Citibank", "UnknownBank"])
def test_unknown_banks_never_use_velo_schedule_parser(bank):
    with pytest.raises(ImportError):
        parse(HEADER.replace("VeloBank S.A.", bank) + ROW1 + ROW2 + ROW3 + "Strona 1 z 1")


def test_schedule_is_not_a_bank_statement_and_blank_image_source_stays_unsupported():
    with pytest.raises(ImportError):
        parse_import(source(HEADER + ROW1 + ROW2 + ROW3 + "Strona 1 z 1"), "statement")
    with pytest.raises(ImportError):
        parse_import(source("", pdf=True), "loan_schedule")


def test_encrypted_pdf_is_rejected_before_schedule_parsing():
    with pytest.raises(ImportError):
        extract_pdf_pages(text_pdf_bytes(HEADER + ROW1 + ROW2 + ROW3, encrypted=True), LIMITS)


@pytest.mark.parametrize(
    "name,numbers,complete",
    [
        ("initial", [1, 2, 3], True),
        ("revised", [1, 2, 3], True),
        ("truncated", [1], False),
        ("renumbered", [1, 2], True),
    ],
)
def test_committed_synthetic_pdfs_extract_to_the_expected_remaining_plan(name, numbers, complete):
    raw = (Path(__file__).parent / "fixtures" / f"velo_schedule_{name}.pdf").read_bytes()
    result = parse_import(
        ParserInput(
            raw, extract_pdf_pages(raw, LIMITS), "application/pdf", hashlib.sha256(raw).hexdigest()
        ),
        "loan_schedule",
    )
    assert isinstance(result, ParsedSchedule)
    assert [row.bank_number for row in result.rows] == numbers
    assert result.complete_tail is complete
