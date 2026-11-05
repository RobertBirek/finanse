"""Transcription only; uncertainty is retained and all arithmetic belongs to Finance."""

import re
import uuid
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.documents.receipt_read_config import ReceiptReadConfig
from app.documents.receipt_read_schemas import ReceiptReadProblem, ReceiptReadProposal
from app.finance.bills_schemas import MAX_SAFE_MINOR
from app.finance.receipt_schemas import (
    ReceiptBody,
    ReceiptDiscountInput,
    ReceiptDiscountShareInput,
    ReceiptLineInput,
    normalize_receipt_name,
)

AMOUNT_PATTERN = r"^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?$"


def parse_receipt_read_amount(value: str | None, *, allow_zero: bool) -> int | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 32 or not re.fullmatch(AMOUNT_PATTERN, value):
        raise ValueError("invalid_amount")
    whole, _, fraction = value.partition(".")
    result = int(whole) * 100 + int(fraction.ljust(2, "0"))
    if result > MAX_SAFE_MINOR or (result == 0 and not allow_zero):
        raise ValueError("invalid_amount")
    return result


class ReadBase(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    @field_validator("name", "source_text", check_fields=False)
    @classmethod
    def bounded_normalized_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        limit = 500 if info.field_name == "source_text" else 2000
        if value is not None and max(len(value), len(normalize_receipt_name(value))) > limit:
            raise ValueError("text_too_long")
        return value


class ReadLine(ReadBase):
    index: StrictInt = Field(ge=0, le=1_000_000)
    name: str | None = Field(max_length=2000)
    amount: str | None = Field(max_length=32, pattern=AMOUNT_PATTERN)
    basis: Literal["before_separate_discount", "after_included_discount", "unknown"]
    source_text: str = Field(max_length=500)
    unreadable: StrictBool

    @model_validator(mode="after")
    def amount_range(self) -> "ReadLine":
        parse_receipt_read_amount(self.amount, allow_zero=True)
        return self


class ReadShare(ReadBase):
    line_index: StrictInt = Field(ge=0, le=1_000_000)
    amount: str | None = Field(max_length=32, pattern=AMOUNT_PATTERN)

    @model_validator(mode="after")
    def amount_range(self) -> "ReadShare":
        parse_receipt_read_amount(self.amount, allow_zero=False)
        return self


class ReadDiscount(ReadBase):
    index: StrictInt = Field(ge=0, le=1_000_000)
    name: str | None = Field(max_length=2000)
    amount: str | None = Field(max_length=32, pattern=AMOUNT_PATTERN)
    kind: Literal["separate", "included", "unknown"]
    shares: list[ReadShare] = Field(max_length=1000)
    source_text: str = Field(max_length=500)

    @model_validator(mode="after")
    def amount_range(self) -> "ReadDiscount":
        parse_receipt_read_amount(self.amount, allow_zero=False)
        return self


class ReceiptReadPayload(ReadBase):
    document_type: Literal["receipt", "unsupported"]
    currency: Literal["PLN", "EUR", "USD"] | None
    printed_total: str | None = Field(max_length=32, pattern=AMOUNT_PATTERN)
    lines: list[ReadLine] = Field(max_length=1000)
    discounts: list[ReadDiscount] = Field(max_length=200)
    warnings: list[
        Literal["truncated", "unreadable", "missing_rows", "unsupported", "ambiguous_discount"]
    ] = Field(max_length=20)

    @model_validator(mode="after")
    def structure(self) -> "ReceiptReadPayload":
        parse_receipt_read_amount(self.printed_total, allow_zero=False)
        indices = {l.index for l in self.lines}
        if len(indices) != len(self.lines) or len({d.index for d in self.discounts}) != len(
            self.discounts
        ):
            raise ValueError("duplicate_indices")
        if sum(len(d.shares) for d in self.discounts) > 5000:
            raise ValueError("too_many_shares")
        for d in self.discounts:
            refs = [s.line_index for s in d.shares]
            if len(set(refs)) != len(refs) or not set(refs) <= indices:
                raise ValueError("invalid_share_reference")
        return self


def validate_receipt_read_intake(payload: ReceiptReadPayload, config: ReceiptReadConfig) -> None:
    if (
        len(payload.lines) > config.max_lines
        or len(payload.discounts) > config.max_discounts
        or sum(len(d.shares) for d in payload.discounts) > config.max_discount_shares
    ):
        raise ValueError("payload_limit")
    for name in [*(l.name for l in payload.lines), *(d.name for d in payload.discounts)]:
        if (
            name is not None
            and max(len(name), len(normalize_receipt_name(name))) > config.item_name_max_chars
        ):
            raise ValueError("payload_name_limit")


def build_receipt_read_proposal(payload: ReceiptReadPayload) -> ReceiptReadProposal:
    problems: list[ReceiptReadProblem] = []
    lines = []
    discounts = []

    def issue(
        code: str,
        message: str,
        *,
        line: int | None = None,
        discount: int | None = None,
        ack: bool = True,
    ) -> None:
        location = (
            f"line/{line}"
            if line is not None
            else f"discount/{discount}"
            if discount is not None
            else "source"
        )
        problems.append(
            ReceiptReadProblem(
                key=f"{location}/{code}",
                code=code,
                line_index=line,
                discount_index=discount,
                message=message,
                requires_ack=ack,
            )
        )

    for l in payload.lines:
        amount = parse_receipt_read_amount(l.amount, allow_zero=True)
        if l.basis == "unknown" or l.unreadable:
            amount = None
            issue(
                "ambiguous_amount",
                "Sprawdź kwotę i podstawę rabatu przy niejasnej pozycji.",
                line=l.index,
            )
        if amount is None:
            issue("missing_amount", "Uzupełnij nieczytelną kwotę produktu.", line=l.index)
        if not l.name or not l.name.strip():
            issue("missing_name", "Uzupełnij nazwę produktu.", line=l.index)
        if l.basis == "after_included_discount":
            issue(
                "included_discount",
                "Kwota produktu zawiera już rabat; sprawdź, czy nie odejmujesz go ponownie.",
                line=l.index,
            )
        lines.append(
            ReceiptLineInput(
                line_key=uuid.UUID(int=l.index + 1), name=l.name or "", amount_minor=amount
            )
        )
    for d in payload.discounts:
        if d.kind == "included":
            issue(
                "included_discount",
                "Ten rabat jest już w kwocie produktu i nie został odjęty drugi raz.",
                discount=d.index,
            )
            continue
        amount = parse_receipt_read_amount(d.amount, allow_zero=False)
        shares = [
            ReceiptDiscountShareInput(
                line_key=uuid.UUID(int=s.line_index + 1),
                amount_minor=parse_receipt_read_amount(s.amount, allow_zero=False),
            )
            for s in d.shares
        ]
        if d.kind == "unknown":
            amount = None
            shares = []
            issue(
                "ambiguous_discount",
                "Potwierdź sposób ujęcia rabatu; nie rozdzielamy go automatycznie.",
                discount=d.index,
            )
        if not shares:
            issue(
                "manual_discount_shares",
                "Wpisz jawne udziały kuponu przy produktach.",
                discount=d.index,
                ack=False,
            )
        discounts.append(
            ReceiptDiscountInput(
                discount_key=uuid.UUID(int=(1 << 64) + d.index + 1),
                name=d.name or "",
                amount_minor=amount,
                shares=shares,
            )
        )
    for code in dict.fromkeys(payload.warnings):
        issue(code, "Sprawdź kompletność odczytu i brakujące lub niejasne pozycje.")
    importable = (
        payload.document_type == "receipt"
        and payload.currency == "PLN"
        and bool(lines)
        and "unsupported" not in payload.warnings
    )
    if not importable:
        issue("unsupported", "Ten wynik nie jest odczytem pozycji paragonu PLN do importu.")
    if payload.printed_total is None:
        issue(
            "missing_printed_total",
            "Nie odczytano sumy z obrazu. Sprawdź ją z zatwierdzonym nagłówkiem.",
        )
    return ReceiptReadProposal(
        body=ReceiptBody(lines=lines, discounts=discounts), problems=problems, importable=importable
    )
