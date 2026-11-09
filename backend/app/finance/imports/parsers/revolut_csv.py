"""The verified Polish ten-column Revolut export: Kwota excludes the separate Opłata."""

import csv
import io
import re
from datetime import datetime
from itertools import pairwise
from typing import Literal, cast

from pydantic import ValidationError

from app.config import settings
from app.finance.imports.contracts import (
    MAX_MINOR_UNITS,
    REVOLUT_CSV_COLUMNS,
    Check,
    Currency,
    ParsedStatement,
    ParserInput,
    SourcePosition,
    StatementRow,
)
from app.finance.imports.errors import ImportError
from app.finance.imports.parsers.money import parse_minor_units

State = Literal["posted", "pending", "reverted", "cancelled", "unknown"]
STATES: dict[str, State] = {
    "ZAKOŃCZONO": "posted",
    "COMPLETED": "posted",
    "PENDING": "pending",
    "REVERTED": "reverted",
    "CANCELLED": "cancelled",
}


def is_revolut_layout(data: ParserInput) -> bool:
    if data.mime_type != "text/csv":
        return False
    try:
        header = next(
            csv.reader(io.StringIO(data.content.decode("utf-8-sig"), newline=""), strict=True)
        )
    except (UnicodeDecodeError, csv.Error, StopIteration):
        return False
    return len(header) == len(REVOLUT_CSV_COLUMNS) and set(header) == set(REVOLUT_CSV_COLUMNS)


def _timestamp(value: str, *, required: bool) -> datetime | None:
    if not value and not required:
        return None
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", value):
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    raise ImportError(
        "csv_timestamp_invalid", "Niepełna data lub nierozpoznany format czasu CSV.", 422
    )


def _money(value: str) -> int:
    return parse_minor_units(value, decimal_separator=".")


def _check(code: str, expected: int, actual: int) -> Check:
    return Check(
        code=code,
        required=True,
        result="passed" if expected == actual else "failed",
        expected=expected if abs(expected) <= MAX_MINOR_UNITS else None,
        actual=actual if abs(actual) <= MAX_MINOR_UNITS else None,
    )


def _chain_matches(rows: list[StatementRow]) -> bool:
    return all(
        previous.balance_after is not None
        and current.balance_after == previous.balance_after + current.amount
        for previous, current in pairwise(rows)
    )


def parse_revolut_csv(data: ParserInput) -> ParsedStatement:
    if not is_revolut_layout(data):
        raise ImportError(
            "layout_unsupported", "CSV nie ma pełnego rozpoznanego kontraktu Revolut.", 422
        )
    if len(data.content) > settings.DOCUMENT_MAX_FILE_BYTES:
        raise ImportError("source_size_limit", "Plik przekracza skonfigurowany limit.", 413)
    if b"\x00" in data.content:
        raise ImportError("csv_invalid", "Niedozwolony znak w CSV.", 422)
    reader = csv.reader(io.StringIO(data.content.decode("utf-8-sig"), newline=""), strict=True)
    headers = next(reader)
    rows: list[StatementRow] = []
    posted_times: list[datetime] = []
    all_times: list[datetime] = []
    currencies: set[str] = set()
    try:
        while True:
            first_line = reader.line_num + 1
            try:
                values = next(reader)
            except StopIteration:
                break
            if not values:
                continue
            if len(values) != len(headers):
                raise ImportError("csv_incomplete_record", "Niepełny rekord CSV.", 422)
            if len(rows) >= settings.FINANCE_IMPORT_MAX_CSV_ROWS:
                raise ImportError(
                    "csv_row_limit", "Przekroczono skonfigurowany limit wierszy.", 413
                )
            raw = dict(zip(headers, values, strict=True))
            currency = raw["Waluta"]
            if currency not in {"PLN", "EUR", "USD"}:
                raise ImportError(
                    "currency_unsupported", "Waluta źródła nie jest obsługiwana.", 422
                )
            currencies.add(currency)
            if len(currencies) != 1:
                raise ImportError(
                    "csv_mixed_currencies", "Wybierz oddzielny wyciąg CSV dla każdej waluty.", 422
                )
            state = STATES.get(raw["State"], "unknown")
            started = _timestamp(raw["Data rozpoczęcia"], required=True)
            completed = _timestamp(raw["Data zrealizowania"], required=state == "posted")
            if started is not None:
                all_times.append(started)
            if completed is not None:
                all_times.append(completed)
                if state == "posted":
                    posted_times.append(completed)
            if state == "posted" and not raw["Saldo"]:
                raise ImportError(
                    "csv_balance_missing", "Zakończony rekord CSV nie zawiera salda.", 422
                )
            fee = _money(raw["Opłata"])
            # Proven on the source export's balance steps: delta = Kwota - Opłata.
            # Never switch semantics/signs in response to a failed reconciliation.
            amount = _money(raw["Kwota"]) - fee
            rows.append(
                StatementRow(
                    key=f"revolut:{first_line}",
                    position=SourcePosition(line=first_line),
                    booking_date=completed.date() if completed else None,
                    operation_date=started.date() if started else None,
                    started_at=raw["Data rozpoczęcia"] or None,
                    completed_at=raw["Data zrealizowania"] or None,
                    description=raw["Opis"],
                    amount=amount,
                    fee=fee,
                    currency=cast(Currency, currency),
                    state=state,
                    balance_after=_money(raw["Saldo"]) if raw["Saldo"] else None,
                    raw={key: value for key, value in raw.items()},
                )
            )
    except (csv.Error, ValidationError) as error:
        raise ImportError(
            "csv_invalid", "Nie udało się odczytać pełnego rekordu CSV.", 422
        ) from error
    if not rows:
        raise ImportError("csv_empty", "CSV nie zawiera operacji.", 422)
    posted = [row for row in rows if row.state == "posted"]
    warnings = ["timestamps_without_timezone"]
    if posted_times != sorted(posted_times):
        if posted_times != sorted(posted_times, reverse=True):
            raise ImportError(
                "csv_order_unsupported", "Kolejność zakończonych operacji wymaga sprawdzenia.", 422
            )
        posted.reverse()
    elif (
        len(posted_times) > 1
        and len(set(posted_times)) == 1
        and not _chain_matches(posted)
        and _chain_matches(list(reversed(posted)))
    ):
        posted.reverse()
        warnings.append("order_from_balances")
    checks = [
        Check(
            code="known_states",
            required=True,
            result="failed" if any(row.state == "unknown" for row in rows) else "passed",
        )
    ]
    opening: int | None = None
    closing: int | None = None
    if posted:
        first_balance = posted[0].balance_after
        assert first_balance is not None
        opening = first_balance - posted[0].amount
        closing = posted[-1].balance_after
        assert closing is not None
        if abs(opening) > MAX_MINOR_UNITS:
            raise ImportError(
                "amount_out_of_range", "Saldo otwarcia przekracza zakres aplikacji.", 422
            )
        warnings.append("opening_derived")
        for previous, row in pairwise(posted):
            assert previous.balance_after is not None and row.balance_after is not None
            checks.append(
                _check(
                    f"balance_after:{row.key}",
                    previous.balance_after + row.amount,
                    row.balance_after,
                )
            )
        checks.append(
            _check("balance_rollforward", closing, opening + sum(row.amount for row in posted))
        )
    else:
        warnings.append("no_posted_movements")
        checks.append(Check(code="balance_rollforward", required=False, result="unavailable"))
    return ParsedStatement(
        bank="revolut",
        layout="revolut-csv-pl-v1",
        parser_version="revolut-csv-pl-v1.0",
        account_reference=None,
        currency=rows[0].currency,
        period_start=min(all_times).date(),
        period_end=max(all_times).date(),
        opening=opening,
        closing=closing,
        rows=rows,
        checks=checks,
        warnings=warnings,
    )
