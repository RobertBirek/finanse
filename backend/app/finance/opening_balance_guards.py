"""BO privileges come from a server link, never a user-supplied description."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.opening_balance_models import AccountOpeningBalance


async def guard_opening_balance_transaction(
    db: AsyncSession,
    owner: uuid.UUID,
    transaction_id: uuid.UUID,
) -> None:
    linked = await db.scalar(
        select(AccountOpeningBalance.id).where(
            AccountOpeningBalance.user_id == owner,
            AccountOpeningBalance.transaction_id == transaction_id,
        )
    )
    if linked is not None:
        raise ValueError("Bilans otwarcia jest chroniony. Użyj edycji BO konta.")
