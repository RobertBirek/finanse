"""Strict decimal text to integer minor units; no float, rounding or separator guessing."""

import re

from app.finance.imports.contracts import MAX_MINOR_UNITS
from app.finance.imports.errors import ImportError


def parse_minor_units(value: str, *, decimal_separator: str) -> int:
    if decimal_separator not in {".", ","}:
        raise ImportError("amount_format_unsupported", "Nieobsługiwany separator kwoty.", 422)
    text = value.strip()
    whole_pattern = r"(?:[0-9]+|[0-9]{1,3}(?:[ \u00a0\u202f][0-9]{3})+)"
    match = re.fullmatch(
        rf"([+-]?)({whole_pattern})(?:{re.escape(decimal_separator)}([0-9]{{2}}))?", text
    )
    if match is None:
        raise ImportError(
            "amount_invalid", "Kwota nie jest pełną liczbą w rozpoznanym formacie.", 422
        )
    digits = re.sub(r"[ \u00a0\u202f]", "", match[2]).lstrip("0") or "0"
    if len(digits) > len(str(MAX_MINOR_UNITS // 100)):
        raise ImportError("amount_out_of_range", "Kwota przekracza zakres aplikacji.", 422)
    amount = int(digits) * 100 + int(match[3] or "0")
    if amount > MAX_MINOR_UNITS:
        raise ImportError("amount_out_of_range", "Kwota przekracza zakres aplikacji.", 422)
    return -amount if match[1] == "-" else amount
