"""Fail closed until an explicitly supported bank layout has a complete parser."""

import re

from app.finance.imports.contracts import ParsedImport, ParserInput
from app.finance.imports.errors import ImportError
from app.finance.imports.parsers.revolut_csv import is_revolut_layout, parse_revolut_csv
from app.finance.imports.parsers.velo_account import is_velo_account, parse_velo_account


def parse_import(data: ParserInput, kind: str) -> ParsedImport:
    if kind not in {"statement", "loan_schedule"}:
        raise ImportError("unsupported_import_kind", "Nieobsługiwany rodzaj importu.", 422)
    if kind == "statement" and is_revolut_layout(data):
        return parse_revolut_csv(data)
    if kind == "statement" and is_velo_account(data):
        return parse_velo_account(data)
    header = "\n".join((data.pages or ())[:1])
    if re.search(r"\b(?:Citibank|Citi\s+Handlowy)\b", header, re.IGNORECASE):
        raise ImportError("bank_unsupported", "Citi nie jest obsługiwany przez importer.", 422)
    # Subsequent parser tasks add explicit layout recognizers here, never fuzzy/AI fallbacks.
    raise ImportError("layout_unsupported", "Układ dokumentu nie jest jeszcze obsługiwany.", 422)
