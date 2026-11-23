"""Small deterministic rules for suggestions, never financial writes."""

import re
import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from app.finance.imports.auto_policy import ExternalKind, classify, normalized_label
from app.finance.imports.contracts import StatementRow


@dataclass(frozen=True)
class Match:
    transaction_id: uuid.UUID
    kind: str
    description: str
    booking_date: date | None
    signed_amount: int
    bank_reference: bool


_ACTUAL_PREFIX = re.compile(
    r"^\[actual:[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\]\s*", re.IGNORECASE
)
_VELO_AMOUNT = re.compile(r"^na kwotę [+-]?\d[\d ]*,\d{2} PLN - (.+)", re.IGNORECASE)


def description_key(description: str) -> str:
    """Drop known wrappers only; keep the merchant text exact."""
    plain = _ACTUAL_PREFIX.sub("", description.strip())
    lines = plain.splitlines()
    if len(lines) > 1 and normalized_label(lines[0]) in {"zakup", "płatność kartą", "card payment"}:
        match = _VELO_AMOUNT.fullmatch(lines[1].strip())
        if match:
            return normalized_label(" ".join([match[1], *lines[2:]]))
    return normalized_label(plain)


def settlement_kind(bank: str, layout: str | None, row: StatementRow) -> ExternalKind | None:
    if row.state != "posted" or not row.amount or row.fee or row.currency != "PLN":
        return None
    if layout != "velo_card_v1":
        return classify(bank, row)[0]
    lines = row.raw.get("description_lines")
    if bank != "velo" or row.amount >= 0 or not isinstance(lines, list) or not lines:
        return None
    labels = [line for line in lines if isinstance(line, str)]
    if len(labels) != len(lines):
        return None
    label = normalized_label(labels[0])
    if label in {"zakup", "odsetki od transakcji gotowkowych", "odsetki od transakcji gotówkowych"}:
        return "expense"
    detail = normalized_label(" ".join(labels[1:]))
    if (
        label == "plan spłat ratalnych „komfort”"
        and "część odsetkowa raty" in detail
        and "część kapitałowa" not in detail
    ):
        return "expense"
    return None


def strict_match(row: StatementRow, candidates: list[Match], used: set[uuid.UUID]) -> Match | None:
    if len(candidates) != 1:
        return None
    match = candidates[0]
    description = description_key(row.description)
    if (
        match.transaction_id not in used
        and match.kind in {"expense", "income"}
        and match.signed_amount == row.amount
        and row.booking_date is not None
        and match.booking_date == row.booking_date
        and (
            match.bank_reference
            or (description and description == description_key(match.description))
        )
    ):
        return match
    return None


def repeated_targets(targets: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    return {target for target, count in Counter(targets).items() if count > 1}


def distinct_category(categories: Iterable[uuid.UUID]) -> uuid.UUID | None:
    unique = set(categories)
    return next(iter(unique)) if len(unique) == 1 else None
