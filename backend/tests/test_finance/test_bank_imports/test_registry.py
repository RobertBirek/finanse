import hashlib

import pytest

from app.finance.imports.contracts import ParserInput
from app.finance.imports.errors import ImportError
from app.finance.imports.parsers.registry import parse_import


@pytest.mark.parametrize("text", ["Citi Handlowy\nWyciag", "Citibank\nStatement"])
def test_citi_is_explicitly_unsupported_without_financial_rows(text: str) -> None:
    data = ParserInput(
        content=b"synthetic",
        pages=(text,),
        mime_type="application/pdf",
        sha256=hashlib.sha256(b"synthetic").hexdigest(),
    )
    with pytest.raises(ImportError) as error:
        parse_import(data, "statement")
    assert error.value.code == "bank_unsupported"


@pytest.mark.parametrize("kind", ["statement", "loan_schedule"])
def test_unknown_pdf_layout_never_becomes_financial_rows(kind: str) -> None:
    data = ParserInput(
        content=b"synthetic",
        pages=("Unknown synthetic document",),
        mime_type="application/pdf",
        sha256=hashlib.sha256(b"synthetic").hexdigest(),
    )
    with pytest.raises(ImportError) as error:
        parse_import(data, kind)
    assert error.value.code == "layout_unsupported"
