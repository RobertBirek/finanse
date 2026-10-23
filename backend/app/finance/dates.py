"""Calendar helpers shared by finance use cases; clock semantics are unchanged."""

from datetime import UTC, date, datetime


def _local_today() -> date:
    """Keep transaction dates aligned with the user's local calendar day."""
    return datetime.now(UTC).astimezone().date()


def _month_bounds(month: int | None, year: int | None) -> tuple[int, int, date, date]:
    now = datetime.now(UTC)
    selected_month = now.month if month is None else month
    selected_year = now.year if year is None else year
    month_start = date(selected_year, selected_month, 1)
    month_end = date(selected_year + (selected_month == 12), (selected_month % 12) + 1, 1)
    return selected_month, selected_year, month_start, month_end


def _add_month(value: date, months: int = 1) -> date:
    month = value.month - 1 + months
    return date(value.year + month // 12, month % 12 + 1, value.day)


def _payday_bounds(today: date, payday_day: int) -> tuple[date, date]:
    current_payday = date(today.year, today.month, payday_day)
    if today >= current_payday:
        return current_payday, _add_month(current_payday)
    return _add_month(current_payday, -1), current_payday
