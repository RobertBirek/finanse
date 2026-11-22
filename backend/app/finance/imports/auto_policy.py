"""Conservative classification from bank fields, not transaction amount alone."""

from typing import Literal

from app.finance.imports.contracts import StatementRow

ExternalKind = Literal["expense", "income"]

_CARD_PURCHASE = {"płatność kartą", "card payment"}
_INTEREST = {"interest", "odsetki", "kapitalizacja odsetek"}


def normalized_label(text: str) -> str:
    return " ".join(text.casefold().replace("_", " ").split())


def classify(bank: str, row: StatementRow) -> tuple[ExternalKind | None, str | None]:
    if row.state != "posted" or not (row.amount or row.fee):
        return None, "not_postable"
    if row.fee:
        return None, "fee_review"
    label: object = None
    if bank == "revolut":
        label = row.raw.get("Rodzaj")
    elif bank in {"velo", "ing"}:
        lines = row.raw.get("description_lines")
        if isinstance(lines, list) and len(lines) >= 2:
            label = lines[0]
    if not isinstance(label, str):
        return None, "movement_unclear"
    label = normalized_label(label)
    if row.amount < 0 and label in _CARD_PURCHASE:
        return "expense", None
    if row.amount > 0 and label in _INTEREST:
        return "income", None
    return None, "movement_unclear"
