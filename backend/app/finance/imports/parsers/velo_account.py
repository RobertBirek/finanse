"""Deterministic Velo account text table, including descriptions across page boundaries."""

import re
from dataclasses import dataclass
from datetime import datetime

from app.finance.imports.contracts import (
    Check,
    ParsedStatement,
    ParserInput,
    SourcePosition,
    StatementRow,
)
from app.finance.imports.errors import ImportError
from app.finance.imports.parsers.money import parse_minor_units

DATE = re.compile(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}")
MONEY = re.compile(r"[+-]?(?:[0-9]+|[0-9]{1,3}(?: [0-9]{3})+),[0-9]{2}(?: (?:WN|MA))?")
COLUMNS = (
    "Data",
    "księgowania",
    "Data",
    "transakcji",
    "Opis transakcji Kwota transakcji",
    "w PLN",
    "Saldo po transakcji",
    "w PLN",
)
SUMMARY = ("Obroty WN", "Obroty MA", "Saldo końcowe")


@dataclass(frozen=True)
class Line:
    text: str
    page: int
    number: int


def _lines(data: ParserInput) -> list[Line]:
    result = []
    for page_index, page in enumerate(data.pages or (), 1):
        lines = [
            Line(" ".join(line.split()), page_index, index)
            for index, line in enumerate(page.splitlines(), 1)
            if line.strip()
        ]
        index = 0
        while index < len(lines):
            if tuple(line.text for line in lines[index : index + len(COLUMNS)]) == COLUMNS:
                index += len(COLUMNS)
                continue
            if lines[index].text.startswith("Infolinia +"):
                footer_end = next(
                    (j for j in range(index, len(lines)) if lines[j].text == "velobank.pl"), None
                )
                if footer_end is not None and any(
                    "VeloBank S.A. z siedzibą" in line.text for line in lines[index:footer_end]
                ):
                    index = footer_end + 1
                    continue
            result.append(lines[index])
            index += 1
    return result


def is_velo_account(data: ParserInput) -> bool:
    if data.mime_type != "application/pdf" or not data.pages:
        return False
    first = " ".join(data.pages[0].split())
    if " ".join(COLUMNS) not in first:
        return False
    return all(
        anchor in first
        for anchor in [
            "VeloBank",
            "Wyciąg za okres od",
            "Waluta rachunku:",
            "Saldo początkowe",
            "Saldo po transakcji",
        ]
    )


def _amount(text: str) -> int:
    direction = text[-2:] if text.endswith((" WN", " MA")) else None
    value = parse_minor_units(text[:-3] if direction else text, decimal_separator=",")
    if direction == "WN":
        return -abs(value)
    if direction == "MA":
        if value < 0:
            raise ImportError(
                "velo_direction_conflict", "Znak kwoty jest sprzeczny z kierunkiem MA.", 422
            )
        return value
    return value


def _date(text: str):
    try:
        return datetime.strptime(text, "%Y.%m.%d").date()
    except ValueError as error:
        raise ImportError("velo_date_invalid", "Nieprawidłowa data w tabeli Velo.", 422) from error


def parse_velo_account(data: ParserInput) -> ParsedStatement:
    if not is_velo_account(data):
        raise ImportError("layout_unsupported", "Nierozpoznany układ wyciągu rachunku Velo.", 422)
    lines = _lines(data)
    first = " ".join(data.pages[0].split()) if data.pages else ""
    period = re.search(r"Wyciąg za okres od ([0-9.]{10}) do ([0-9.]{10})", first)
    account = re.search(r"Numer rachunku: ([0-9]{2}(?: [0-9]{4}){6})(?![0-9])", first)
    currency = re.search(r"Waluta rachunku: ([A-Z]{3})", first)
    if period is None or account is None or currency is None or currency[1] != "PLN":
        raise ImportError(
            "velo_header_incomplete", "Nagłówek wyciągu Velo wymaga sprawdzenia.", 422
        )
    start, end = _date(period[1]), _date(period[2])
    if end < start:
        raise ImportError("velo_period_invalid", "Nieprawidłowy okres wyciągu Velo.", 422)
    opening_index = next(
        (i for i, line in enumerate(lines) if line.text.startswith("Saldo początkowe ")), None
    )
    if opening_index is None:
        raise ImportError("velo_opening_missing", "Brak salda początkowego wyciągu.", 422)
    opening = _amount(lines[opening_index].text.removeprefix("Saldo początkowe "))
    summary_index = next(
        (
            i
            for i in range(opening_index + 1, len(lines))
            if tuple(line.text for line in lines[i : i + 3]) == SUMMARY
        ),
        None,
    )
    body = lines[opening_index + 1 : summary_index]
    checks: list[Check] = []

    def check(
        code: str, passed: bool, *, expected: int | None = None, actual: int | None = None
    ) -> None:
        checks.append(
            Check(
                code=code,
                required=True,
                result="passed" if passed else "failed",
                expected=expected,
                actual=actual,
            )
        )

    rows = []
    index = 0
    previous_balance = opening
    while index < len(body):
        first_line = body[index]
        if (
            not DATE.fullmatch(first_line.text)
            or index + 1 >= len(body)
            or not DATE.fullmatch(body[index + 1].text)
        ):
            check(f"unmatched_line:{first_line.page}:{first_line.number}", False)
            index += 1
            continue
        booking, operation = _date(first_line.text), _date(body[index + 1].text)
        stop = index + 2
        while stop < len(body) and not (
            DATE.fullmatch(body[stop].text)
            and stop + 1 < len(body)
            and DATE.fullmatch(body[stop + 1].text)
        ):
            stop += 1
        fields = body[index + 2 : stop]
        amounts = [line for line in fields if MONEY.fullmatch(line.text)]
        description = [line.text for line in fields if not MONEY.fullmatch(line.text)]
        if len(amounts) != 2 or not description:
            check(f"incomplete_row:{first_line.page}:{first_line.number}", False)
            index = stop
            continue
        amount, balance = _amount(amounts[0].text), _amount(amounts[1].text)
        key = f"velo:{first_line.page}:{first_line.number}"
        check(
            f"balance_after:{key}",
            previous_balance + amount == balance,
            expected=previous_balance + amount,
            actual=balance,
        )
        check(f"booking_period:{key}", start <= booking <= end)
        rows.append(
            StatementRow(
                key=key,
                position=SourcePosition(page=first_line.page, line=first_line.number),
                booking_date=booking,
                operation_date=operation,
                description="\n".join(description),
                amount=amount,
                fee=0,
                currency="PLN",
                state="posted",
                balance_after=balance,
                raw={
                    "booking_date": first_line.text,
                    "operation_date": body[index + 1].text,
                    "amount": amounts[0].text,
                    "balance_after": amounts[1].text,
                    "description_lines": [line for line in description],
                },
            )
        )
        previous_balance = balance
        index = stop
    closing = None
    complete_summary = (
        summary_index is not None and len(lines[summary_index + 3 : summary_index + 6]) == 3
    )
    if complete_summary and summary_index is not None:
        values = lines[summary_index + 3 : summary_index + 6]
        complete_summary = all(MONEY.fullmatch(line.text) for line in values)
        if complete_summary:
            debit, credit, closing = (_amount(line.text) for line in values)
            actual_debit = sum(row.amount for row in rows if row.amount < 0)
            actual_credit = sum(row.amount for row in rows if row.amount > 0)
            check("debit_total", debit == actual_debit, expected=debit, actual=actual_debit)
            check("credit_total", credit == actual_credit, expected=credit, actual=actual_credit)
            check(
                "closing_balance",
                previous_balance == closing,
                expected=closing,
                actual=previous_balance,
            )
            check(
                "rollforward",
                opening + actual_debit + actual_credit == closing,
                expected=closing,
                actual=opening + actual_debit + actual_credit,
            )
    check("complete_summary", bool(complete_summary))
    if summary_index is not None:
        for line in lines[summary_index + 6 :]:
            if DATE.fullmatch(line.text) or MONEY.fullmatch(line.text) or line.text in SUMMARY:
                check(f"unmatched_tail:{line.page}:{line.number}", False)
    return ParsedStatement(
        bank="velo",
        layout="velo-account-pdf-v1",
        parser_version="velo-account-pdf-v1.0",
        account_reference=account[1].replace(" ", ""),
        currency="PLN",
        period_start=start,
        period_end=end,
        opening=opening,
        closing=closing,
        rows=rows,
        checks=checks,
        warnings=[],
    )
