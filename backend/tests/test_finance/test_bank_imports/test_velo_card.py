import hashlib

import pytest

from app.finance.imports.contracts import ParserInput
from app.finance.imports.parsers.registry import parse_import
from app.finance.imports.parsers.velo_card import parse_velo_card
from app.finance.imports.pdf_text import PdfLimits, extract_pdf_pages
from tests.test_finance.test_bank_imports.factories import text_pdf_bytes

COLUMNS = "Data\nksięgowania\nData\ntransakcji\nOpis transakcji Kwota transakcji w PLN\n"
HEADER = (
    "VeloBank S.A.\nWyciąg numer 1/2026 z rachunku karty kredytowej\n"
    "Wyciąg za okres od 2026.01.01 do 2026.01.31\nPODSUMOWANIE RACHUNKU\n"
    "PRZYZNANY LIMIT KREDYTOWY 10 000,00 PLN\n"
    "SALDO ZADŁUŻENIA NA KONIEC OKRESU ROZLICZENIOWEGO 920,00 PLN\n"
    "MINIMALNA KWOTA DO SPŁATY 50,00 PLN\nTERMIN SPŁATY 2026.02.15\n"
    "TWÓJ RACHUNEK KARTY KREDYTOWEJ 00 0000 0000 0000 0000 0000 0000\n"
    "Poprzednie saldo zadłużenia 1 000,00 PLN\nZESTAWIENIE TRANSAKCJI\n"
)
CARD = "ZESTAWIENIE TRANSAKCJI DLA KARTY numer ****1111 Synthetic Person\n"
PAYMENT = "2026.01.02\n2026.01.01\nSpłata\nSynthetic repayment 100,00 PLN - title\n100,00\n"
PURCHASE = "2026.01.03\n2026.01.02\nZakup\nSynthetic purchase -10,00 PLN - merchant\n-10,00\n"


def source(*pages: str) -> ParserInput:
    content = "\n".join(pages).encode()
    return ParserInput(
        content=content,
        pages=pages,
        mime_type="application/pdf",
        sha256=hashlib.sha256(content).hexdigest(),
    )


def card_statement():
    return parse_velo_card(source(HEADER + CARD + COLUMNS + PAYMENT + PURCHASE + PURCHASE))


def failed(result) -> list[str]:
    return [check.code for check in result.checks if check.required and check.result != "passed"]


def test_card_header_is_separate_from_posted_account_movements() -> None:
    result = card_statement()
    assert result.layout == "velo_card_v1" and len(result.rows) == 3 and not failed(result)
    assert [row.amount for row in result.rows] == [10000, -1000, -1000]
    assert result.opening == -100000 and result.closing == -92000
    assert result.card_header is not None
    assert result.card_header["cycle_debt_pln"] == 92000
    assert result.card_header["minimum_pln"] == 5000
    assert result.card_header["credit_limit_pln"] == 1000000
    assert result.card_header["total_debt_pln"] is None
    assert result.card_header["future_installment_principal_pln"] is None
    assert all(
        row.balance_after is None and row.position.section == "card:1111" for row in result.rows
    )
    assert (
        parse_import(source(HEADER + CARD + COLUMNS + PAYMENT + PURCHASE + PURCHASE), "statement")
        == result
    )


def test_same_description_date_amount_within_one_card_keeps_two_real_purchases() -> None:
    result = card_statement()
    purchases = result.rows[1:]
    assert len({row.key for row in purchases}) == 2 and purchases[0].raw == purchases[1].raw
    assert not failed(result)


def test_cross_section_repeat_cannot_be_deduplicated_just_to_fit_debt() -> None:
    text = HEADER + CARD + COLUMNS + PAYMENT + PURCHASE + PURCHASE
    text += CARD.replace("1111", "2222") + COLUMNS + PAYMENT + PURCHASE + PURCHASE
    result = parse_velo_card(source(text))
    assert len(result.rows) == 6
    assert "ambiguous_section_repeat" in failed(result) and "debt_rollforward" in failed(result)


def test_unrecognized_repeated_card_section_is_not_silently_folded() -> None:
    text = HEADER + CARD + COLUMNS + PAYMENT + PURCHASE + PURCHASE + CARD + COLUMNS
    result = parse_velo_card(source(text))
    assert "duplicate_card_section" in failed(result)


def test_actual_polish_card_pdf_is_extracted_before_parser() -> None:
    raw = text_pdf_bytes(HEADER + CARD + COLUMNS + PAYMENT, COLUMNS + PURCHASE + PURCHASE)
    pages = extract_pdf_pages(raw, PdfLimits(1024 * 1024, 10, 20000, 5, 256 * 1024 * 1024))
    result = parse_velo_card(
        ParserInput(
            content=raw,
            pages=pages,
            mime_type="application/pdf",
            sha256=hashlib.sha256(raw).hexdigest(),
        )
    )
    assert len(result.rows) == 3 and not failed(result)


@pytest.mark.parametrize(
    "change",
    [
        lambda text: text.replace("920,00 PLN", "921,00 PLN"),
        lambda text: text.removesuffix("-10,00\n"),
        lambda text: text + "7,77\n",
        lambda text: text.replace("2026.01.03\n2026.01.02", "2026.01.03", 1),
    ],
)
def test_incomplete_or_conflicting_table_never_becomes_importable(change) -> None:
    result = parse_velo_card(
        source(change(HEADER + CARD + COLUMNS + PAYMENT + PURCHASE + PURCHASE))
    )
    assert failed(result)


def test_unknown_metadata_does_not_invent_zero_or_block_independently_valid_table() -> None:
    text = (HEADER + CARD + COLUMNS + PAYMENT + PURCHASE + PURCHASE).replace(
        "MINIMALNA KWOTA DO SPŁATY 50,00 PLN\n", ""
    )
    result = parse_velo_card(source(text))
    assert not failed(result) and result.card_header is not None
    assert result.card_header["minimum_pln"] is None
    assert "card_metadata_incomplete" in result.warnings


def test_negative_cycle_debt_is_not_silently_converted_to_positive_debt() -> None:
    text = (HEADER + CARD + COLUMNS + PAYMENT + PURCHASE + PURCHASE).replace(
        "920,00 PLN", "-920,00 PLN"
    )
    result = parse_velo_card(source(text))
    assert failed(result) and result.card_header is not None
    assert result.card_header["cycle_debt_pln"] == -92000


def test_labelled_total_and_future_installment_details_are_not_new_card_movements() -> None:
    text = HEADER + CARD + COLUMNS + PAYMENT + PURCHASE + PURCHASE
    text += "Łączna suma transakcji\n80,00\nSZCZEGÓŁY DOTYCZĄCE PLANÓW RATALNYCH\n"
    text += "Opis transakcji Data transakcji Kwota transakcji Kapitał\npozostały do\nspłacenia\n"
    text += "Synthetic future plan 2026.01.01 500,00 PLN 400,00 PLN 4 10,00 %\nData i godzina: 2026-02-01 12:00:00\n"
    result = parse_velo_card(source(text))
    assert len(result.rows) == 3 and not failed(result)
    assert result.card_header is not None and result.card_header["total_debt_pln"] is None
    assert result.card_header["installment_details_text"]


def test_labelled_total_is_a_required_check_not_a_reason_to_delete_repeated_purchases() -> None:
    text = (
        HEADER + CARD + COLUMNS + PAYMENT + PURCHASE + PURCHASE + "Łączna suma transakcji\n90,00\n"
    )
    result = parse_velo_card(source(text))
    assert len(result.rows) == 3 and "printed_transaction_total" in failed(result)
