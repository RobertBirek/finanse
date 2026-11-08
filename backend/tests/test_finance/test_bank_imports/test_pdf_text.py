from dataclasses import replace

import pytest

from app.finance.imports.errors import ImportError
from app.finance.imports.pdf_text import PdfLimits, extract_pdf_pages
from tests.test_finance.test_bank_imports.factories import text_pdf_bytes


@pytest.fixture
def limits() -> PdfLimits:
    return PdfLimits(
        max_bytes=1024 * 1024,
        max_pages=5,
        max_text_chars=5000,
        timeout_seconds=5,
        max_memory_bytes=256 * 1024 * 1024,
    )


def test_real_pdf_text_preserves_page_and_row_order(limits: PdfLimits) -> None:
    pages = extract_pdf_pages(text_pdf_bytes("First page\nRow 1", "Second page\nRow 2"), limits)
    assert len(pages) == 2
    assert pages[0].splitlines() == ["First page", "Row 1"]
    assert pages[1].splitlines() == ["Second page", "Row 2"]


@pytest.mark.parametrize("content", [b"", b"%PDF-invalid", b"PK\x03\x04spreadsheet"])
def test_not_a_complete_pdf_has_no_extracted_rows(content: bytes, limits: PdfLimits) -> None:
    with pytest.raises(ImportError):
        extract_pdf_pages(content, limits)


def test_encrypted_pdf_never_requests_or_retains_password(limits: PdfLimits) -> None:
    with pytest.raises(ImportError) as error:
        extract_pdf_pages(text_pdf_bytes("Private", encrypted=True), limits)
    assert error.value.code == "pdf_encrypted"
    assert "Private" not in str(error.value)


@pytest.mark.parametrize("pages", [("",), ("Valid table", "")])
def test_empty_or_mixed_image_only_page_cannot_be_silently_skipped(
    pages: tuple[str, ...],
    limits: PdfLimits,
) -> None:
    with pytest.raises(ImportError) as error:
        extract_pdf_pages(text_pdf_bytes(*pages), limits)
    assert error.value.code == "pdf_requires_text"


def test_configured_page_limit_blocks_truncated_output(limits: PdfLimits) -> None:
    with pytest.raises(ImportError) as error:
        extract_pdf_pages(text_pdf_bytes("Page 1", "Page 2"), replace(limits, max_pages=1))
    assert error.value.code == "pdf_page_limit"


def test_configured_text_limit_does_not_return_a_partial_table(limits: PdfLimits) -> None:
    with pytest.raises(ImportError) as error:
        extract_pdf_pages(text_pdf_bytes("A" * 100), replace(limits, max_text_chars=10))
    assert error.value.code == "pdf_text_limit"


def test_configured_byte_limit_is_checked_before_pdf_process(limits: PdfLimits) -> None:
    with pytest.raises(ImportError) as error:
        extract_pdf_pages(text_pdf_bytes("Row"), replace(limits, max_bytes=10))
    assert error.value.http_status == 413


def test_parser_wall_clock_timeout_is_bounded(limits: PdfLimits) -> None:
    with pytest.raises(ImportError) as error:
        extract_pdf_pages(
            text_pdf_bytes("Synthetic table"), replace(limits, timeout_seconds=0.000001)
        )
    assert error.value.code == "pdf_timeout"


def test_parser_memory_failure_does_not_return_partial_text(limits: PdfLimits) -> None:
    with pytest.raises(ImportError) as error:
        extract_pdf_pages(text_pdf_bytes("Synthetic table"), replace(limits, max_memory_bytes=4096))
    assert error.value.code == "pdf_resource_limit"
