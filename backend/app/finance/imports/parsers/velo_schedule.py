"""Strict Velo remaining-plan table; its values never represent completed payments."""

import re
from datetime import date
from itertools import pairwise

from pydantic import ValidationError

from app.finance.imports.contracts import (
    Check,
    ParsedSchedule,
    ParserInput,
    ScheduleRow,
    SourcePosition,
)
from app.finance.imports.errors import ImportError
from app.finance.imports.parsers.money import parse_minor_units

MONEY = r"(?:[0-9]+|[0-9]{1,3}(?:\s[0-9]{3})+),[0-9]{2}"
COLUMNS = re.compile(
    r"Nr\s+raty:\s+Data\s+raty:\s+Rata\s+kapitałowa\s+\(PLN\)\s+"
    r"Rata\s+odsetkowa\s+\(PLN\)\s+Rata\s+łącznie\s+\(PLN\)\s+"
    r"Saldo\s+zadłużenia\s+kredytu\s+po\s+spłacie\s+raty\s+\(PLN\)",
    re.IGNORECASE,
)
ROW = re.compile(
    rf"(?m)^\s*(?P<number>[0-9]+)\s+(?P<due>[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}})\s+"
    rf"(?P<principal>{MONEY})\s+(?P<interest>{MONEY})\s+(?P<total>{MONEY})\s+(?P<balance>{MONEY})\s*(?=\n|$)"
)
PAGE = re.compile(r"^\s*Strona\s+([0-9]+)\s+z\s+([0-9]+)\s*$", re.IGNORECASE)
RESIDUAL = re.compile(
    rf"^\s*Saldo\s+pozostałe\s+po\s+zakończeniu\s+harmonogramu\s+\(PLN\):\s*({MONEY})\s*$",
    re.IGNORECASE,
)
EFFECTIVE = re.compile(
    r"od\s+kiedy\s+obowiązuje\s+nowy\s+harmonogram\s+([0-9]{4}-[0-9]{2}-[0-9]{2})", re.IGNORECASE
)


def is_velo_schedule(data: ParserInput) -> bool:
    if data.mime_type != "application/pdf" or not data.pages:
        return False
    header = "\n".join(data.pages[:2])
    return bool(
        re.search(r"\bVeloBank\s+S\.A\.", header, re.IGNORECASE)
        and re.search(r"Harmonogram\s+spłat(?:y\s+kredytu)?\b", header, re.IGNORECASE)
    )


def _minor(value: str) -> int:
    return parse_minor_units(re.sub(r"\s+", " ", value), decimal_separator=",")


def parse_velo_schedule(data: ParserInput) -> ParsedSchedule:
    if not is_velo_schedule(data):
        raise ImportError("layout_unsupported", "Nieobsługiwany układ harmonogramu Velo.", 422)
    pages = tuple(page.replace("\xa0", " ").replace("\u202f", " ") for page in data.pages or ())
    text = "\n".join(pages)
    columns = [COLUMNS.search(page) for page in pages]
    first_page = next((i for i, match in enumerate(columns) if match), None)
    if first_page is None:
        raise ImportError("layout_unsupported", "Brak jednoznacznych kolumn harmonogramu PLN.", 422)
    effective_values = EFFECTIVE.findall(text)
    effective = None
    if effective_values and len(set(effective_values)) == 1:
        try:
            effective = date.fromisoformat(effective_values[0])
        except ValueError:
            pass
    references = re.findall(r"numer\s+umowy\s+kredytu\s+([^\s]+)", text, re.IGNORECASE)
    reference = references[0] if references and len(set(references)) == 1 else None
    checks: list[Check] = []

    def check(code: str, passed: bool) -> None:
        checks.append(Check(code=code, required=True, result="passed" if passed else "failed"))

    check("schedule_effective_date", effective is not None)
    check("schedule_reference_consistency", len(set(references)) <= 1)
    # Only this exact table has no fee column. Equality of its two named components
    # and the named total confirms zero, rather than guessing a missing component.
    check(
        "schedule_currency_columns",
        not bool(re.search(r"\((?:EUR|USD)\)|Opłaty\s*\(", text, re.IGNORECASE)),
    )
    body: list[str] = []
    positions: list[tuple[int, int]] = []
    page_structure = True
    residuals: list[int] = []
    for page_index in range(first_page, len(pages)):
        page = pages[page_index]
        column = columns[page_index]
        start = column.end() if column else 0
        # Keep line positions even after removing a repeated header or page footer.
        prefix_lines = page[:start].count("\n")
        markers: list[tuple[int, int]] = []
        for line_index, line in enumerate(page[start:].splitlines(), prefix_lines + 1):
            marker = PAGE.fullmatch(line)
            if marker:
                markers.append((int(marker[1]), int(marker[2])))
                continue
            residual = RESIDUAL.fullmatch(line)
            if residual:
                residuals.append(_minor(residual[1]))
                continue
            body.append(line)
            positions.append((page_index + 1, line_index))
        if markers != [(page_index + 1, len(pages))]:
            page_structure = False
    check("schedule_pages_complete", page_structure)
    raw_body = "\n".join(body)
    rows: list[ScheduleRow] = []
    occupied = bytearray(len(raw_body))
    components_valid = True
    for match in ROW.finditer(raw_body):
        occupied[match.start() : match.end()] = b"1" * (match.end() - match.start())
        line_index = raw_body[: match.start("number")].count("\n")
        page_number, line_number = positions[line_index]
        try:
            row = ScheduleRow(
                bank_number=int(match["number"]),
                due_date=date.fromisoformat(match["due"]),
                principal=_minor(match["principal"]),
                interest=_minor(match["interest"]),
                fees=0,
                total=_minor(match["total"]),
                balance_after=_minor(match["balance"]),
                position=SourcePosition(
                    page=page_number, line=line_number, section="loan_schedule"
                ),
            )
        except (ValueError, ValidationError, ImportError):
            components_valid = False
            continue
        rows.append(row)
    check(
        "schedule_table_consumed",
        all(occupied[i] or char.isspace() for i, char in enumerate(raw_body)),
    )
    check("schedule_components", bool(rows) and components_valid)
    numbers = [row.bank_number for row in rows]
    if len(numbers) != len(set(numbers)):
        raise ImportError(
            "schedule_duplicate_number", "Numery rat w źródle nie są jednoznaczne.", 422
        )
    check("schedule_number_sequence", bool(numbers) and numbers == list(range(1, len(numbers) + 1)))
    check(
        "schedule_due_dates",
        bool(rows) and all(a.due_date < b.due_date for a, b in pairwise(rows)),
    )
    check(
        "schedule_balance_chain",
        bool(rows)
        and all(
            a.balance_after is not None
            and b.balance_after is not None
            and a.balance_after - b.principal == b.balance_after
            for a, b in pairwise(rows)
        ),
    )
    expected_final = residuals[0] if len(residuals) == 1 else 0
    check(
        "schedule_terminal_balance",
        bool(rows) and len(residuals) <= 1 and rows[-1].balance_after == expected_final,
    )
    complete = all(c.result == "passed" for c in checks)
    return ParsedSchedule(
        bank="velo",
        layout="velo_remaining_schedule_pln_v1",
        parser_version="1",
        loan_reference=reference,
        effective_date=effective,
        rows=rows,
        checks=checks,
        warnings=[]
        if complete
        else ["Harmonogram nie przeszedł pełnej kontroli; aktywacja zablokowana."],
        complete_tail=complete,
    )
