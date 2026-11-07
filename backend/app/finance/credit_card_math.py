"""Deterministic minor-unit calculations; estimates never create ledger entries."""

from calendar import monthrange
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

MAX_MONEY = 9_007_199_254_740_991


def card_position(limit: int, posted_balance: int, pending_debits: int) -> dict[str, int]:
    debt = max(0, -posted_balance)
    return {
        "debt_pln": debt,
        "available_pln": max(0, limit - debt - pending_debits),
        "overpayment_pln": max(0, posted_balance),
        "overlimit_pln": max(0, debt + pending_debits - limit),
        "pending_debits_pln": pending_debits,
        "posted_balance_pln": posted_balance,
    }


def _valid_rate(rate: Decimal) -> None:
    if not rate.is_finite() or not Decimal(0) <= rate <= Decimal(100):
        raise ValueError("APR must be finite and between 0 and 100 percent")


def estimate_schedule(
    principal: int,
    apr: Decimal,
    count: int,
    first_due: date,
    fees: int,
) -> list[dict]:
    """Equal principal, APR/12, half-up cents, fees in first installment.

    Explicitly an estimate: banks can use different day counts/annuity schedules.
    """
    _valid_rate(apr)
    if (
        not 1 <= principal <= MAX_MONEY
        or not 1 <= count <= min(600, principal)
        or not 0 <= fees <= MAX_MONEY
    ):
        raise ValueError("Invalid plan principal, installment count or fees")
    result = []
    remaining = principal
    for index in range(count):
        month_index = first_due.year * 12 + first_due.month - 1 + index
        year, month = divmod(month_index, 12)
        due = date(year, month + 1, min(first_due.day, monthrange(year, month + 1)[1]))
        part = remaining if index == count - 1 else principal // count
        interest = int(
            (Decimal(remaining) * apr / 1200).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        )
        if part + interest + (fees if index == 0 else 0) > MAX_MONEY:
            raise ValueError("Estimated installment exceeds safe integer limit")
        result.append(
            {
                "number": index + 1,
                "due_date": due,
                "principal_pln": part,
                "interest_pln": interest,
                "fees_pln": fees if index == 0 else 0,
            }
        )
        remaining -= part
    return result


def estimate_daily_interest(principal: int, apr: Decimal, days: int) -> int:
    """Simple ACT/365 example, not a bank statement or grace-period decision."""
    _valid_rate(apr)
    if not 0 <= principal <= MAX_MONEY or not 0 <= days <= 3660:
        raise ValueError("Invalid estimate principal or days")
    result = int(
        (Decimal(principal) * apr * days / 36500).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    )
    if result > MAX_MONEY:
        raise ValueError("Estimated interest exceeds safe integer limit")
    return result
