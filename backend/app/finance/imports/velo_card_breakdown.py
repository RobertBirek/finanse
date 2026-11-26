"""Derive a card statement preview from immutable import evidence."""

import re
from datetime import date
from typing import Literal

from pydantic import ValidationError

from app.finance.imports.auto_policy import normalized_label
from app.finance.imports.contracts import MAX_MINOR_UNITS, ParsedStatement, StatementRow
from app.finance.imports.errors import ImportError
from app.finance.imports.parsers.money import parse_minor_units
from app.finance.imports.schemas import VeloCardBreakdown, VeloCardCharge, VeloCardInstallment

_PLAN_PREFIX = "uruchomienie planu spłat ratalnych"
_PLN = r"(?:[0-9]+|[0-9]{1,3}(?: [0-9]{3})+),[0-9]{2}"
_KOMFORT_PLAN = re.compile(
    rf"{_PLAN_PREFIX} (?P<date>[0-9]{{4}}\.[0-9]{{2}}\.[0-9]{{2}}) "
    rf"(?P<original>{_PLN}) pln (?P<remaining>{_PLN}) pln [0-9]+ [0-9]+,[0-9]{{2}} % „komfort”"
)
_KOMFORT_CHARGE = re.compile(
    rf"(?:na kwotę [+-]?{_PLN} pln - )?"
    r"część (kapitałowa|odsetkowa) raty planu spłat ratalnych „komfort”"
)
_CASH_INTEREST = {"odsetki od transakcji gotowkowych", "odsetki od transakcji gotówkowych"}


def _statement_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _minor_units(value: object, *, minimum: int = 0) -> int | None:
    if type(value) is int and minimum <= value <= MAX_MINOR_UNITS:
        return value
    return None


def _plan_principal(value: object, period_end: date) -> tuple[int, int] | None:
    if not isinstance(value, list) or not all(isinstance(line, str) for line in value):
        return None
    lines = [normalized_label(line) for line in value]
    plan_lines = [index for index, line in enumerate(lines) if line.startswith(_PLAN_PREFIX)]
    if len(plan_lines) != 1:
        return None
    index = plan_lines[0]
    line = lines[index]
    if lines[index + 1 : index + 2] == ["„komfort”"]:
        line += " „komfort”"
    plan = _KOMFORT_PLAN.fullmatch(line)
    if plan is None:
        return None
    started = _statement_date(plan["date"].replace(".", "-"))
    if started is None or started > period_end:
        return None
    try:
        original = parse_minor_units(plan["original"], decimal_separator=",")
        remaining = parse_minor_units(plan["remaining"], decimal_separator=",")
    except ImportError:
        return None
    return (original, remaining) if original > 0 and remaining <= original else None


def _charge(row: StatementRow) -> VeloCardCharge | None:
    if (
        row.state != "posted"
        or row.amount >= 0
        or row.fee
        or row.currency != "PLN"
        or row.booking_date is None
    ):
        return None
    label, _, detail = row.description.partition("\n")
    label = normalized_label(label)
    kind: Literal["principal", "plan_interest", "cash_interest"]
    if label in _CASH_INTEREST:
        kind = "cash_interest"
    elif label == "plan spłat ratalnych „komfort”":
        component = _KOMFORT_CHARGE.fullmatch(normalized_label(detail))
        if component is None:
            return None
        kind = "principal" if component[1] == "kapitałowa" else "plan_interest"
    else:
        return None
    return VeloCardCharge(
        row_key=row.key, kind=kind, booking_date=row.booking_date, amount_pln=-row.amount
    )


def velo_card_breakdown(result: dict[str, object] | None) -> VeloCardBreakdown | None:
    if (
        result is None
        or result.get("bank") != "velo"
        or result.get("layout") != "velo_card_v1"
        or result.get("currency") != "PLN"
    ):
        return None
    try:
        statement = ParsedStatement.model_validate(result)
    except ValidationError:
        return None
    header = statement.card_header or {}
    due = _statement_date(header.get("due_date"))
    minimum = _minor_units(header.get("minimum_pln"))
    plan_principal = _plan_principal(
        header.get("installment_details_text"), statement.period_end
    )
    future_principal = plan_principal[1] if plan_principal else None
    installment_charges = []
    cash_interest = []
    for row in statement.rows:
        charge = _charge(row)
        if charge is None:
            continue
        if charge.kind == "cash_interest":
            cash_interest.append(charge)
        else:
            installment_charges.append((row, charge))

    installment = None
    if (
        future_principal is not None
        and len(installment_charges) == 2
        and all(not check.required or check.result == "passed" for check in statement.checks)
    ):
        (first_row, first), (second_row, second) = installment_charges
        total = first.amount_pln + second.amount_pln
        if (
            first.kind != second.kind
            and first.booking_date == second.booking_date
            and first_row.operation_date == second_row.operation_date
            and first_row.position.section is not None
            and first_row.position.section == second_row.position.section
            and total <= MAX_MINOR_UNITS
        ):
            principal, interest = (first, second) if first.kind == "principal" else (second, first)
            installment = VeloCardInstallment(
                principal_pln=principal.amount_pln,
                interest_pln=interest.amount_pln,
                total_pln=total,
                # Velo's Komfort terms include the due installment in the minimum.
                included_in_minimum=minimum is not None and total <= minimum,
            )
    return VeloCardBreakdown(
        due_date=due if due is not None and due > statement.period_end else None,
        cycle_debt_pln=_minor_units(header.get("cycle_debt_pln"), minimum=-MAX_MINOR_UNITS),
        minimum_pln=minimum,
        installment_original_principal_pln=plan_principal[0] if plan_principal else None,
        future_installment_principal_pln=future_principal,
        komfort_installment=installment,
        unassigned_installment_charges=(
            [charge for _, charge in installment_charges] if installment is None else []
        ),
        cash_interest_charges=cash_interest,
    )
