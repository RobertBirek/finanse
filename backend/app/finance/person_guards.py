"""Protect attributed gift identity without granting new ledger editing powers."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.person_models import FinancePerson, PersonTransactionLink


async def guard_person_gift_change(
    db: AsyncSession, owner: uuid.UUID, transaction_id: uuid.UUID, changes: set[str]
) -> None:
    if changes <= {"description", "project_id"}:
        return
    linked = await db.scalar(
        select(PersonTransactionLink.id).where(
            PersonTransactionLink.user_id == owner,
            PersonTransactionLink.transaction_id == transaction_id,
        )
    )
    if linked is not None:
        raise ValueError("Darowizna jest powiązana z osobą; najpierw odepnij osobę.")


async def guard_person_reference_account_change(
    db: AsyncSession, owner: uuid.UUID, account_id: uuid.UUID, changes: dict[str, object]
) -> None:
    if "delete" not in changes and changes.get("is_budget_account") is not True:
        return
    linked = await db.scalar(
        select(FinancePerson.id).where(
            FinancePerson.user_id == owner,
            FinancePerson.reference_account_id == account_id,
        )
    )
    if linked is not None:
        raise ValueError("Konto ma skrót do osoby; najpierw odepnij konto w profilu osoby.")
