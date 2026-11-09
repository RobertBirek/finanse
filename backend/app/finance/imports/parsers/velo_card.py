"""Velo card movements and statement facts, never debt inferred from a credit limit."""

import re
from collections import Counter

from app.finance.imports.contracts import (
    Check,
    ParsedStatement,
    ParserInput,
    SourcePosition,
    StatementRow,
)
from app.finance.imports.errors import ImportError
from app.finance.imports.parsers.money import parse_minor_units
from app.finance.imports.parsers.velo_account import DATE, MONEY, Line, _date

COLUMNS = ("Data", "księgowania", "Data", "transakcji", "Opis transakcji Kwota transakcji w PLN")
SECTION = re.compile(r"ZESTAWIENIE TRANSAKCJI DLA KARTY numer \*{4}([0-9]{4})(?: .*)?")


def is_velo_card(data: ParserInput) -> bool:
    if data.mime_type != "application/pdf" or not data.pages:
        return False
    first = " ".join(data.pages[0].split())
    return (
        "VeloBank" in first
        and "z rachunku karty kredytowej" in first
        and " ".join(COLUMNS) in first
    )


def parse_velo_card(data: ParserInput) -> ParsedStatement:
    if not is_velo_card(data):
        raise ImportError("layout_unsupported", "Nierozpoznany układ wyciągu karty Velo.", 422)
    assert data.pages is not None
    lines = [
        Line(" ".join(line.split()), p, i)
        for p, page in enumerate(data.pages, 1)
        for i, line in enumerate(page.splitlines(), 1)
        if line.strip()
    ]
    first_section = next((i for i, line in enumerate(lines) if SECTION.fullmatch(line.text)), None)
    if first_section is None:
        raise ImportError("card_identity_missing", "Brak identyfikacji sekcji karty.", 422)
    header_text = " ".join(line.text for line in lines[:first_section])
    period = re.search(r"Wyciąg za okres od ([0-9.]{10}) do ([0-9.]{10})", header_text)
    account = re.search(
        r"(?:TWÓJ )?RACHUNEK KARTY KREDYTOWEJ ([0-9]{2}(?: [0-9]{4}){6})(?![0-9])", header_text
    )
    if period is None or account is None:
        raise ImportError(
            "card_header_incomplete", "Niepełny okres lub rachunek wyciągu karty.", 422
        )
    start, end = _date(period[1]), _date(period[2])
    if end < start:
        raise ImportError("card_period_invalid", "Nieprawidłowy okres wyciągu karty.", 422)

    def header_amount(label: str) -> int | None:
        matches = re.findall(re.escape(label) + r" ([+-]?[0-9 ]+,[0-9]{2}) PLN", header_text)
        if len(matches) != 1:
            return None
        return parse_minor_units(matches[0], decimal_separator=",")

    previous_debt = header_amount("Poprzednie saldo zadłużenia")
    cycle_debt = header_amount("SALDO ZADŁUŻENIA NA KONIEC OKRESU ROZLICZENIOWEGO")
    if previous_debt is None or cycle_debt is None:
        raise ImportError("card_balances_missing", "Brak niezależnych sald wyciągu karty.", 422)
    minimum = header_amount("MINIMALNA KWOTA DO SPŁATY")
    limit = header_amount("PRZYZNANY LIMIT KREDYTOWY")
    due_match = re.findall(r"TERMIN SPŁATY ([0-9.]{10})", header_text)
    due = _date(due_match[0]) if len(due_match) == 1 else None
    checks: list[Check] = []

    def check(code: str, passed: bool) -> None:
        checks.append(Check(code=code, required=True, result="passed" if passed else "failed"))

    body: list[tuple[Line, str]] = []
    section = ""
    sections: Counter[str] = Counter()
    index = first_section
    ended = False
    printed_total: int | None = None
    installment_text: list[str] = []
    while index < len(lines):
        line = lines[index]
        if line.text.startswith("Data i godzina:"):
            ended = True
        if ended:
            if DATE.fullmatch(line.text) or MONEY.fullmatch(line.text):
                check(f"unmatched_tail:{line.page}:{line.number}", False)
            index += 1
            continue
        label = SECTION.fullmatch(line.text)
        if label:
            section = "card:" + label[1]
            sections[section] += 1
            index += 1
            continue
        if line.text == "Łączna suma transakcji":
            if index + 1 < len(lines) and MONEY.fullmatch(lines[index + 1].text):
                printed_total = parse_minor_units(lines[index + 1].text, decimal_separator=",")
                index += 2
                continue
            check("printed_transaction_total", False)
            index += 1
            continue
        if line.text == "SZCZEGÓŁY DOTYCZĄCE PLANÓW RATALNYCH":
            index += 1
            while index < len(lines) and not lines[index].text.startswith("Data i godzina:"):
                installment_text.append(lines[index].text)
                index += 1
            continue
        if tuple(item.text for item in lines[index : index + len(COLUMNS)]) == COLUMNS:
            index += len(COLUMNS)
            continue
        if re.fullmatch(r"Strona [0-9]+ z [0-9]+", line.text):
            index += 1
            continue
        body.append((line, section))
        index += 1
    check("duplicate_card_section", all(count == 1 for count in sections.values()))
    rows = []
    index = 0
    while index < len(body):
        line, section = body[index]
        if (
            not DATE.fullmatch(line.text)
            or index + 1 >= len(body)
            or not DATE.fullmatch(body[index + 1][0].text)
        ):
            check(f"unmatched_line:{line.page}:{line.number}", False)
            index += 1
            continue
        stop = index + 2
        while (
            stop < len(body)
            and body[stop][1] == section
            and not (
                DATE.fullmatch(body[stop][0].text)
                and stop + 1 < len(body)
                and DATE.fullmatch(body[stop + 1][0].text)
            )
        ):
            stop += 1
        fields = [item[0].text for item in body[index + 2 : stop]]
        amounts = [text for text in fields if MONEY.fullmatch(text)]
        description = [text for text in fields if not MONEY.fullmatch(text)]
        if len(amounts) != 1 or not description:
            check(f"incomplete_row:{line.page}:{line.number}", False)
            index = stop
            continue
        booking = _date(line.text)
        operation = _date(body[index + 1][0].text)
        check(f"booking_period:{line.page}:{line.number}", start <= booking <= end)
        rows.append(
            StatementRow(
                key=f"velo-card:{line.page}:{line.number}",
                position=SourcePosition(page=line.page, line=line.number, section=section),
                booking_date=booking,
                operation_date=operation,
                description="\n".join(description),
                amount=parse_minor_units(amounts[0], decimal_separator=","),
                fee=0,
                currency="PLN",
                state="posted",
                balance_after=None,
                raw={
                    "booking_date": line.text,
                    "operation_date": body[index + 1][0].text,
                    "amount": amounts[0],
                    "description_lines": [text for text in description],
                },
            )
        )
        index = stop
    seen: dict[tuple[object, ...], set[str]] = {}
    for row in rows:
        signature = (row.booking_date, row.operation_date, row.description, row.amount)
        seen.setdefault(signature, set()).add(row.position.section or "")
    # Similar purchases within one section remain independent occurrences. Cross-card
    # repeats lack a verified bank identity: preserve every row and block, never fit sums.
    check(
        "ambiguous_section_repeat",
        not any(len(card_sections) > 1 for card_sections in seen.values()),
    )
    check("debt_rollforward", -previous_debt + sum(row.amount for row in rows) == -cycle_debt)
    if printed_total is not None:
        check("printed_transaction_total", printed_total == sum(row.amount for row in rows))
    metadata_complete = (
        minimum is not None and minimum >= 0 and due is not None and due > end and cycle_debt >= 0
    )
    return ParsedStatement(
        bank="velo",
        layout="velo_card_v1",
        parser_version="velo-card-v1.0",
        account_reference=account[1].replace(" ", ""),
        currency="PLN",
        period_start=start,
        period_end=end,
        opening=-previous_debt,
        closing=-cycle_debt,
        rows=rows,
        checks=checks,
        warnings=[
            "source_has_no_row_balances",
            *([] if metadata_complete else ["card_metadata_incomplete"]),
        ],
        card_header={
            "debt_definition": "current_cycle",
            "cycle_debt_pln": cycle_debt,
            "previous_debt_pln": previous_debt,
            "minimum_pln": minimum,
            "due_date": due.isoformat() if due else None,
            "credit_limit_pln": limit,
            "total_debt_pln": None,
            "future_installment_principal_pln": None,
            "installment_details_text": [text for text in installment_text],
        },
    )
