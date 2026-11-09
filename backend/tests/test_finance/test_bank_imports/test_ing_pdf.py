import hashlib
from datetime import date

import pytest

from app.finance.imports.contracts import ParserInput
from app.finance.imports.errors import ImportError
from app.finance.imports.parsers.ing import parse_ing_statement
from app.finance.imports.parsers.registry import parse_import
from app.finance.imports.pdf_text import PdfLimits, extract_pdf_pages
from tests.test_finance.test_bank_imports.factories import text_pdf_bytes

COLUMNS = (
    "Data księgowania\n/ Data transakcji Dane kontrahenta Tytuł Szczegóły / nr transakcji Kwota\n"
)
HEADER = (
    "Nr 1 / 01.01.2026 - 31.03.2026\nWyciąg z rachunku\nNazwa rachunku:\nKONTO Z LWEM Direct\n"
    "Waluta rachunku:\nPLN\nNr rachunku/NRB:\n00 0000 0000 0000 0000 0000 0000\n"
    "Saldo początkowe\n/ saldo końcowe poprzedniego wyciągu:\n1 000,00 PLN\n"
    "Suma uznań (1):\n25,00 PLN\nSaldo końcowe:\n1 015,00 PLN\nSuma obciążeń (1):\n10,00 PLN\n"
)
FIRST = (
    "02.01.2026\n01.01.2026\nSynthetic payment\nSynthetic title\n123456789012345678 -10,00 PLN\n"
)
SECOND = "03.03.2026\n02.03.2026\nSynthetic transfer\n25,00 PLN\n"


def source(*pages: str) -> ParserInput:
    raw = "\n".join(pages).encode()
    return ParserInput(
        content=raw,
        pages=pages,
        mime_type="application/pdf",
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def failed(result) -> list[str]:
    return [check.code for check in result.checks if check.required and check.result != "passed"]


def test_direct_multimonth_source_keeps_all_dates_amounts_and_header_controls() -> None:
    result = parse_ing_statement(source(HEADER + COLUMNS + FIRST + SECOND))
    assert result.layout == "ing_direct_v1" and result.bank == "ing" and result.currency == "PLN"
    assert result.period_start == date(2026, 1, 1) and result.period_end == date(2026, 3, 31)
    assert (result.period_end - result.period_start).days > 31 and not failed(result)
    assert result.opening == 100000 and result.closing == 101500
    assert [row.amount for row in result.rows] == [-1000, 2500]
    assert all(row.balance_after is None and row.fee == 0 for row in result.rows)
    assert result.rows[0].operation_date == date(2026, 1, 1)
    assert "Synthetic title" in result.rows[0].description
    assert result.account_reference == "00000000000000000000000000"
    assert parse_import(source(HEADER + COLUMNS + FIRST + SECOND), "statement") == result


def test_ing_real_pdf_preserves_polish_header_and_multiline_table() -> None:
    raw = text_pdf_bytes(HEADER + COLUMNS + FIRST, COLUMNS + SECOND)
    pages = extract_pdf_pages(raw, PdfLimits(1024 * 1024, 10, 20000, 5, 256 * 1024 * 1024))
    result = parse_ing_statement(
        ParserInput(
            content=raw,
            pages=pages,
            mime_type="application/pdf",
            sha256=hashlib.sha256(raw).hexdigest(),
        )
    )
    assert len(result.rows) == 2 and result.rows[1].position.page == 2 and not failed(result)


def test_page_continuation_after_amount_still_belongs_to_the_previous_payment() -> None:
    result = parse_ing_statement(
        source(
            HEADER + COLUMNS + FIRST + "Strona: 1 z 2. Wyciąg z rachunku\n",
            COLUMNS
            + "Continuation of synthetic counterparty\n"
            + SECOND
            + "Strona: 2 z 2. Wyciąg z rachunku\n",
        )
    )
    assert len(result.rows) == 2 and not failed(result)
    assert "Continuation of synthetic counterparty" in result.rows[0].description


@pytest.mark.parametrize(
    "change",
    [
        lambda text: text.replace("25,00 PLN\n", "26,00 PLN\n", 1),
        lambda text: text.replace("Suma obciążeń (1)", "Suma obciążeń (2)"),
        lambda text: text.replace("1 015,00 PLN", "1 016,00 PLN"),
        lambda text: text.removesuffix("25,00 PLN\n"),
        lambda text: text + "7,77 PLN\n",
        lambda text: text.replace("03.03.2026\n02.03.2026", "03.03.2026"),
    ],
)
def test_missing_row_amount_date_or_inconsistent_header_totals_block_source(change) -> None:
    result = parse_ing_statement(source(change(HEADER + COLUMNS + FIRST + SECOND)))
    assert failed(result)


def test_two_similar_payments_never_merge_based_on_description_and_amount() -> None:
    header = (
        HEADER.replace("Suma uznań (1):\n25,00", "Suma uznań (0):\n0,00")
        .replace("Suma obciążeń (1):\n10,00", "Suma obciążeń (2):\n20,00")
        .replace("1 015,00", "980,00")
    )
    result = parse_ing_statement(source(header + COLUMNS + FIRST + FIRST))
    assert (
        len(result.rows) == 2 and len({row.key for row in result.rows}) == 2 and not failed(result)
    )


def test_known_footer_is_not_a_payment_or_part_of_description() -> None:
    footer = "Środki pieniężne zgromadzone na rachunku bankowym podlegają ochronie gwarancyjnej\nING Bank Śląski S.A.\nStrona: 1 z 1. Wyciąg z rachunku\n"
    result = parse_ing_statement(source(HEADER + COLUMNS + FIRST + SECOND + footer))
    assert not failed(result) and "ochronie" not in result.rows[-1].description


def test_missing_page_is_explicitly_blocked_even_if_summary_amounts_happen_to_fit() -> None:
    result = parse_ing_statement(
        source(HEADER + COLUMNS + FIRST + SECOND + "Strona: 1 z 2. Wyciąg z rachunku\n")
    )
    assert "complete_pages" in failed(result)


def test_empty_direct_table_can_be_a_real_no_movement_statement() -> None:
    header = (
        HEADER.replace("Suma uznań (1):\n25,00", "Suma uznań (0):\n0,00")
        .replace("Suma obciążeń (1):\n10,00", "Suma obciążeń (0):\n0,00")
        .replace("1 015,00", "1 000,00")
    )
    result = parse_ing_statement(source(header + COLUMNS))
    assert result.rows == [] and not failed(result)


def test_savings_layout_is_explicitly_deferred_not_guessed_from_direct_columns() -> None:
    with pytest.raises(ImportError) as error:
        parse_ing_statement(
            source(
                (HEADER + COLUMNS).replace("KONTO Z LWEM Direct", "Otwarte Konto Oszczędnościowe")
            )
        )
    assert error.value.code == "layout_unsupported"


@pytest.mark.parametrize(
    "text",
    [
        "Unknown bank",
        HEADER.replace("PLN", "EUR") + COLUMNS + FIRST,
        HEADER.replace("Nr rachunku/NRB:", "Unknown account:") + COLUMNS,
    ],
)
def test_unrecognized_source_never_inherits_currency_or_account_from_another_file(
    text: str,
) -> None:
    with pytest.raises(ImportError):
        parse_ing_statement(source(text))
