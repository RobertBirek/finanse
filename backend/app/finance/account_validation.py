"""Small, dependency-free validation for optional account bank metadata."""

import re

from pydantic import ValidationInfo

_BIC_PATTERN = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?$")

# ISO 13616 country formats (length includes country code and check digits).
# Protocol constraints, not financial settings or a bank-name inference table.
IBAN_LENGTHS = {
    "AD": 24,
    "AE": 23,
    "AL": 28,
    "AT": 20,
    "AZ": 28,
    "BA": 20,
    "BE": 16,
    "BG": 22,
    "BH": 22,
    "BI": 27,
    "BR": 29,
    "BY": 28,
    "CH": 21,
    "CR": 22,
    "CY": 28,
    "CZ": 24,
    "DE": 22,
    "DJ": 27,
    "DK": 18,
    "DO": 28,
    "EE": 20,
    "EG": 29,
    "ES": 24,
    "FI": 18,
    "FK": 18,
    "FO": 18,
    "FR": 27,
    "GB": 22,
    "GE": 22,
    "GI": 23,
    "GL": 18,
    "GR": 27,
    "GT": 28,
    "HR": 21,
    "HU": 28,
    "IE": 22,
    "IL": 23,
    "IQ": 23,
    "IS": 26,
    "IT": 27,
    "JO": 30,
    "KW": 30,
    "KZ": 20,
    "LB": 28,
    "LC": 32,
    "LI": 21,
    "LT": 20,
    "LU": 20,
    "LV": 21,
    "LY": 25,
    "MC": 27,
    "MD": 24,
    "ME": 22,
    "MK": 19,
    "MN": 20,
    "MR": 27,
    "MT": 31,
    "MU": 30,
    "NI": 28,
    "NL": 18,
    "NO": 15,
    "OM": 23,
    "PK": 24,
    "PL": 28,
    "PS": 29,
    "PT": 25,
    "QA": 29,
    "RO": 24,
    "RS": 22,
    "RU": 33,
    "SA": 24,
    "SC": 31,
    "SD": 18,
    "SE": 24,
    "SI": 19,
    "SK": 24,
    "SM": 27,
    "SO": 23,
    "ST": 25,
    "SV": 28,
    "TL": 23,
    "TN": 24,
    "TR": 26,
    "UA": 29,
    "VA": 22,
    "VG": 24,
    "XK": 20,
}


def normalize_iban(value: str | None, _: ValidationInfo) -> str | None:
    if value is None:
        return None
    compact = "".join(value.upper().split())
    if compact.isdigit() and len(compact) == 26:
        compact = f"PL{compact}"
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]+", compact):
        raise ValueError("Invalid IBAN format")
    if len(compact) != IBAN_LENGTHS.get(compact[:2]):
        raise ValueError("Invalid IBAN country or length")
    if compact.startswith("PL") and not compact[2:].isdigit():
        raise ValueError("Polish account number must contain only digits")
    checksum_digits = "".join(
        char if char.isdigit() else str(ord(char) - ord("A") + 10)
        for char in compact[4:] + compact[:4]
    )
    if int(checksum_digits) % 97 != 1:
        raise ValueError("Invalid IBAN checksum")
    return compact


def normalize_bic(value: str | None, _: ValidationInfo) -> str | None:
    if value is None:
        return None
    compact = value.strip().upper()
    if not _BIC_PATTERN.fullmatch(compact):
        raise ValueError("Invalid BIC format")
    return compact
