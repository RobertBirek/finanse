"""Verified ING Direct PDF family. Savings is explicitly deferred pending plaintext samples."""

import re
from datetime import date, datetime

from app.finance.imports.contracts import (
    Check,
    ParsedStatement,
    ParserInput,
    SourcePosition,
    StatementRow,
)
from app.finance.imports.errors import ImportError
from app.finance.imports.parsers.money import parse_minor_units

COLUMNS = (
    "Data księgowania",
    "/ Data transakcji Dane kontrahenta Tytuł Szczegóły / nr transakcji Kwota",
)
DATE = re.compile(r"[0-9]{2}\.[0-9]{2}\.[0-9]{4}")
AMOUNT = re.compile(r"(?<![0-9])([+-]?(?:[0-9]+|[0-9]{1,3}(?: [0-9]{3})+),[0-9]{2}) PLN$")
PAGE = re.compile(r"Strona: ([0-9]+) z ([0-9]+)\.\s*Wyciąg z rachunku")


def is_ing_direct(data: ParserInput) -> bool:
    if data.mime_type != "application/pdf" or not data.pages:
        return False
    first = " ".join(data.pages[0].split())
    return (
        "Wyciąg z rachunku" in first
        and "KONTO Z LWEM Direct" in first
        and " ".join(COLUMNS) in first
    )


def _date(value: str) -> date:
    try:
        return datetime.strptime(value, "%d.%m.%Y").date()
    except ValueError as error:
        raise ImportError("ing_date_invalid", "Nieprawidłowa data źródła ING.", 422) from error


def _money(value: str) -> int:
    return parse_minor_units(value, decimal_separator=",")


def parse_ing_statement(data: ParserInput) -> ParsedStatement:
    if not is_ing_direct(data):
        raise ImportError(
            "layout_unsupported",
            "Układ ING nie jest obsługiwany; oszczędnościowe odłożono do weryfikacji próbek.",
            422,
        )
    assert data.pages is not None
    lines: list[tuple[str, int, int]] = []
    page_numbers = []
    for page_number, page in enumerate(data.pages, 1):
        page_lines = [
            (" ".join(line.split()), page_number, number)
            for number, line in enumerate(page.splitlines(), 1)
            if line.strip()
        ]
        index = 0
        while index < len(page_lines):
            text = page_lines[index][0]
            page_label = PAGE.fullmatch(text)
            if page_label:
                page_numbers.append((int(page_label[1]), int(page_label[2])))
                index += 1
                continue
            if tuple(item[0] for item in page_lines[index : index + 2]) == COLUMNS:
                # Keep a single header boundary: it separates totals from the table.
                if not any(item[0] == COLUMNS[0] for item in lines):
                    lines.append(page_lines[index])
                index += 2
                continue
            if text.startswith(
                "Środki pieniężne zgromadzone na rachunku bankowym podlegają ochronie gwarancyjnej"
            ):
                end = next(
                    (
                        j
                        for j in range(index + 1, len(page_lines))
                        if page_lines[j][0].startswith("ING Bank Śląski")
                    ),
                    None,
                )
                if end is not None:
                    index = end + 1
                    continue
            lines.append(page_lines[index])
            index += 1
    boundary = next((i for i, item in enumerate(lines) if item[0] == COLUMNS[0]), None)
    if boundary is None:
        raise ImportError("ing_header_incomplete", "Brak nagłówka tabeli ING.", 422)
    header = [item[0] for item in lines[:boundary]]
    header_text = " ".join(header)
    period = re.search(r"Nr [0-9]+ / ([0-9.]{10}) - ([0-9.]{10})", header_text)
    account = re.search(r"Nr rachunku/NRB: ([0-9]{2}(?: [0-9]{4}){6})(?![0-9])", header_text)
    currency = re.search(r"Waluta rachunku: ([A-Z]{3})", header_text)
    if period is None or account is None or currency is None or currency[1] != "PLN":
        raise ImportError(
            "ing_header_incomplete", "Niepełny okres, waluta lub rachunek źródła ING.", 422
        )
    start, end_date = _date(period[1]), _date(period[2])
    if end_date < start:
        raise ImportError("ing_period_invalid", "Nieprawidłowy okres źródła ING.", 422)

    def header_amount(pattern: str) -> int:
        match = re.search(pattern + r" ([+-]?[0-9 ]+,[0-9]{2}) PLN", header_text)
        if match is None:
            raise ImportError("ing_summary_incomplete", "Brak kompletnych sum wyciągu ING.", 422)
        return _money(match[1])

    opening = header_amount(r"Saldo początkowe / saldo końcowe poprzedniego wyciągu:")
    closing = header_amount(r"Saldo końcowe:")
    credit_match = re.search(r"Suma uznań \(([0-9]+)\):", header_text)
    debit_match = re.search(r"Suma obciążeń \(([0-9]+)\):", header_text)
    if credit_match is None or debit_match is None:
        raise ImportError("ing_summary_incomplete", "Brak liczby operacji w wyciągu ING.", 422)
    credits = header_amount(r"Suma uznań \([0-9]+\):")
    debits = header_amount(r"Suma obciążeń \([0-9]+\):")
    checks: list[Check] = []

    def check(code: str, passed: bool) -> None:
        checks.append(Check(code=code, required=True, result="passed" if passed else "failed"))

    body = lines[boundary + 1 :]
    rows = []
    index = 0
    while index < len(body):
        first_line, page_number, number = body[index]
        if (
            not DATE.fullmatch(first_line)
            or index + 1 >= len(body)
            or not DATE.fullmatch(body[index + 1][0])
        ):
            check(f"unmatched_line:{page_number}:{number}", False)
            index += 1
            continue
        stop = index + 2
        while stop < len(body) and not (
            DATE.fullmatch(body[stop][0])
            and stop + 1 < len(body)
            and DATE.fullmatch(body[stop + 1][0])
        ):
            stop += 1
        fields = [item[0] for item in body[index + 2 : stop]]
        matches = [
            (i, match)
            for i, text in enumerate(fields)
            if (match := AMOUNT.search(text)) is not None
        ]
        if len(matches) != 1:
            check(f"incomplete_row:{page_number}:{number}", False)
            index = stop
            continue
        amount_index, match = matches[0]
        amount_page = body[index + 2 + amount_index][1]
        continuation = body[index + 3 + amount_index : stop]
        if any(item[1] <= amount_page or DATE.fullmatch(item[0]) for item in continuation):
            check(f"incomplete_row:{page_number}:{number}", False)
            index = stop
            continue
        prefix = fields[amount_index][: match.start()].strip()
        description = [
            *fields[:amount_index],
            *([prefix] if prefix else []),
            *fields[amount_index + 1 :],
        ]
        if not description:
            check(f"missing_description:{page_number}:{number}", False)
            index = stop
            continue
        booking, operation = _date(first_line), _date(body[index + 1][0])
        check(f"booking_period:{page_number}:{number}", start <= booking <= end_date)
        key = f"ing:{page_number}:{number}"
        rows.append(
            StatementRow(
                key=key,
                position=SourcePosition(page=page_number, line=number),
                booking_date=booking,
                operation_date=operation,
                description="\n".join(description),
                amount=_money(match[1]),
                fee=0,
                currency="PLN",
                state="posted",
                balance_after=None,
                raw={
                    "booking_date": first_line,
                    "operation_date": body[index + 1][0],
                    "amount": match[1],
                    "description_lines": [line for line in description],
                },
            )
        )
        index = stop
    actual_credit = sum(row.amount for row in rows if row.amount > 0)
    actual_debit = -sum(row.amount for row in rows if row.amount < 0)
    check("credit_total", credits == actual_credit)
    check("debit_total", debits == actual_debit)
    check("credit_count", int(credit_match[1]) == sum(row.amount > 0 for row in rows))
    check("debit_count", int(debit_match[1]) == sum(row.amount < 0 for row in rows))
    check("rollforward", opening + actual_credit - actual_debit == closing)
    if page_numbers:
        check(
            "complete_pages",
            page_numbers == [(i, len(data.pages)) for i in range(1, len(data.pages) + 1)],
        )
    return ParsedStatement(
        bank="ing",
        layout="ing_direct_v1",
        parser_version="ing-direct-v1.0",
        account_reference=account[1].replace(" ", ""),
        currency="PLN",
        period_start=start,
        period_end=end_date,
        opening=opening,
        closing=closing,
        rows=rows,
        checks=checks,
        warnings=["source_has_no_row_balances"],
    )
