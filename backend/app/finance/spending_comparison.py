from datetime import date, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.dates import _local_today
from app.finance.reporting import spending_postings

PeriodDays = Literal[14, 30, 90]
_LIMIT = 5


class CategoryChange(BaseModel):
    category_id: UUID
    name: str
    delta_pln: int


class TransactionContribution(BaseModel):
    transaction_id: UUID
    date: date
    description: str
    delta_pln: int


class SpendingComparisonResult(BaseModel):
    previous_start: date
    current_start: date
    end_exclusive: date
    previous_total_pln: int
    current_total_pln: int
    delta_pln: int
    categories: list[CategoryChange]
    transactions: list[TransactionContribution]
    truncated: bool


async def get_spending_comparison(
    db: AsyncSession, user_id: UUID, *, days: PeriodDays, today: date | None = None
) -> SpendingComparisonResult:
    today = today or _local_today()
    previous_start = today - timedelta(days=2 * days)
    current_start = today - timedelta(days=days)
    previous = current = 0
    category_totals: dict[UUID, tuple[str, int]] = {}
    transaction_totals: dict[UUID, tuple[date, str, int]] = {}
    result = await db.stream(spending_postings(user_id, previous_start, today))
    async for txn_id, day, description, category_id, name, raw_amount in result:
        if not previous_start <= day < today:
            continue
        amount = int(raw_amount)
        if day >= current_start:
            current += amount
            delta = amount
        else:
            previous += amount
            delta = -amount
        category_totals[category_id] = (
            name,
            category_totals.get(category_id, (name, 0))[1] + delta,
        )
        transaction_totals[txn_id] = (
            day,
            description,
            transaction_totals.get(txn_id, (day, description, 0))[2] + delta,
        )
    categories = sorted(
        (
            CategoryChange(category_id=key, name=name, delta_pln=delta)
            for key, (name, delta) in category_totals.items()
            if delta
        ),
        key=lambda row: (-abs(row.delta_pln), row.category_id),
    )
    transactions = sorted(
        (
            TransactionContribution(
                transaction_id=key, date=day, description=description, delta_pln=delta
            )
            for key, (day, description, delta) in transaction_totals.items()
            if delta
        ),
        key=lambda row: (-abs(row.delta_pln), row.transaction_id),
    )
    return SpendingComparisonResult(
        previous_start=previous_start,
        current_start=current_start,
        end_exclusive=today,
        previous_total_pln=previous,
        current_total_pln=current,
        delta_pln=current - previous,
        categories=categories[:_LIMIT],
        transactions=transactions[:_LIMIT],
        truncated=len(categories) > _LIMIT or len(transactions) > _LIMIT,
    )
