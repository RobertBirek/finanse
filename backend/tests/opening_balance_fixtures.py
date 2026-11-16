"""Synthetic owner-tampering setup must preserve the new owner-safe BO metadata."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.models import Account
from app.finance.opening_balance_models import AccountOpeningBalance


async def change_zero_opening_account_owner(
    db: AsyncSession,
    account: Account,
    owner: uuid.UUID,
) -> None:
    """Deliberately make a foreign-account fixture, never a production operation."""
    row = await db.scalar(
        select(AccountOpeningBalance).where(
            AccountOpeningBalance.account_id == account.id,
        )
    )
    assert row is not None and row.transaction_id is None
    date, version = row.opening_date, row.version
    await db.delete(row)
    await db.flush()
    account.user_id = owner
    await db.flush()
    db.add(
        AccountOpeningBalance(
            user_id=owner,
            account_id=account.id,
            opening_date=date,
            version=version,
        )
    )
    await db.flush()
